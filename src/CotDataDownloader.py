import logging
import os
import requests
import schedule
import shutil
import ssl
import time
import smtplib
import yaml
import zipfile

from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from CotDatabase import CotDatabase
import utils

# Ensure directories exist
log_file_name = "logs/" + utils.main_cot_logger_file
os.makedirs(os.path.dirname(log_file_name), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_name),
        logging.StreamHandler()
    ]
)

class CotDataDownloader:
    """Class to manage downloading and extracting CFTC data zip files."""
    def __init__(self, data_dir='data/cot_data', xls_data_dir='data/xls_data', param_dir='config/params.yaml', send_email=True):
        self.data_dir = data_dir
        self.xls_data_dir = xls_data_dir
        self.param_dir = param_dir
        self.cot_file_name = "dea_fut_xls_"
        self.url_prefix = "https://www.cftc.gov/files/dea/history/" + self.cot_file_name
        self.enable_email_notifications = send_email

        self.years = []
        self.load_years()

        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.xls_data_dir, exist_ok=True)

        self.cotDatabase = CotDatabase()

    def load_years(self):
        with open(self.param_dir, 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for year in yaml_data["years"]:
                self.years.append(year)

            if datetime.now().year not in self.years:
                utils.downloader_logger.error(f"Current year {datetime.now().year} not found in {self.param_dir}. Adding it to the list of years to check.")
                self.years.append(datetime.now().year)

    def check_zip_updates(self):
        """Schedule zip updates for every Friday at 15:30 EST."""
        # Use 'US/Eastern' time for the schedule
        # Note: Ensure your system clock is in EST or handle offset
        schedule.every().friday.at("15:30").do(self.run_download_retry_loop)

        utils.downloader_logger.info("Scheduler active: Waiting for Friday at 3:30 PM EST.")

        while True:
            schedule.run_pending()
            time.sleep(60)

        utils.downloader_logger.info("Scheduler started: Checking for updates every Friday at 3:30 PM EST.")

    def run_download_retry_loop(self):
        """Retries the update every 2 minutes until the current year's data is found."""
        current_year = datetime.now().year
        success = False
        max_attempts = 30
        attempt = 0

        utils.downloader_logger.info("Scheduler triggered... looking for new data")
        while not success and attempt < max_attempts:
            attempt += 1
            utils.downloader_logger.info(f"Friday Update Attempt {attempt} for year {current_year}...")

            updated = self.check_and_update_zip_files()
            if current_year in updated:
                utils.downloader_logger.info(f"Successfully captured {current_year} data.")
                success = True
            else:
                utils.downloader_logger.info("New data not available yet. Waiting 2 minutes to retry...")
                time.sleep(120)  # Wait 2 minutes between retries

            if not success:
                utils.downloader_logger.error(f"Failed to find new {current_year} data after {max_attempts} attempts.")

    def check_zip_updates_periodic(self, sleep_interval=3600):
        """Check for zip updates every hour."""
        self.cotDatabase = CotDatabase()

        while True:
            utils.downloader_logger.info("Starting the zip file update check.")
            self.check_and_update_zip_files()
            time.sleep(sleep_interval)

    def get_last_modified(self, year):
        """Get the last modified date for the zip file from the server."""
        url = self.url_prefix + f'{year}.zip'
        response = requests.get(url, stream=True)
        return response.headers.get('Last-Modified')

    def download_and_extract_zip(self, url, year):
        zip_file_path = os.path.join(self.data_dir, f'{self.cot_file_name}{year}.zip')
        response = requests.get(url, stream=True)
        with open(zip_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=512):
                if chunk:
                    f.write(chunk)

        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(self.xls_data_dir)
            list_of_file_names = zip_ref.namelist()
            file_name = list_of_file_names[0]

            extracted_file_path = os.path.join(self.xls_data_dir, file_name)
            new_file_path = os.path.join(self.xls_data_dir, f'{year}.xls')

            if os.path.exists(new_file_path):
                try:
                    os.remove(new_file_path)
                except PermissionError as e:
                    utils.get_cot_logger().error(f"Could not delete {new_file_path}: {e}")
                    return

            try:
                shutil.move(extracted_file_path, new_file_path)
                utils.get_cot_logger().info(f"Renamed extracted file to: {new_file_path}")
            except PermissionError as e:
                utils.get_cot_logger().error(f"Error renaming file {extracted_file_path} to {new_file_path}: {e}")

    def send_email_notification(self, updated_years):
        """Send an email notification listing the years with new files downloaded."""
        sender_email = os.environ.get("EMAIL_USER")
        receiver_email = os.environ.get("RECEIVER_EMAIL_USER")
        password = os.environ.get("EMAIL_PASSWORD")
        utils.get_cot_logger().info(f"Sending email notification to {receiver_email}")

        subject = "New COT Zip Files Downloaded"
        body = "The following years had new zip files downloaded:\n\n" + "\n".join(map(str, updated_years))

        # Create a multipart email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject

        # Attach the email body to the message
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=context)
                server.login(sender_email, password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
            utils.downloader_logger.info(f"Email notification successfully sent for updated years: {', '.join(map(str, updated_years))}")
        except Exception as e:
            utils.downloader_logger.error(f"Failed to send email notification: {e}")


    def run_polling_window(self, attempts=20, interval_minutes=1):
        """Polls periodically for a set number of attempts."""
        utils.downloader_logger.info(f"Starting daily polling window ({attempts} attempts, {interval_minutes}m apart)...")

        for attempt in range(1, attempts + 1):
            updated_years = self.check_and_update_zip_files()

            if updated_years:
                utils.downloader_logger.warning(f"New file detected and downloaded on attempt {attempt}! Closing polling window.")
                return  # Exit the loop early since we got the file

            # Wait interval_minutes minutes before checking again
            time.sleep(interval_minutes * 60)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        utils.downloader_logger.warning(f"Polling window ended ({current_time}). No new data found.")


    def check_for_database_updates(self):
        """Schedule the polling window for every weekday at 15:25 Local Time."""
        # Initialize DB here to avoid SQLite multiprocessing lock issues
        self.cotDatabase = CotDatabase()

        # Schedule for every weekday at the CFTC release time (15:25 Local Time)
        database_release_time = "15:25"
        schedule.every().monday.at(database_release_time).do(self.run_polling_window, attempts=20, interval_minutes=1)
        schedule.every().tuesday.at(database_release_time).do(self.run_polling_window, attempts=20, interval_minutes=1)
        schedule.every().wednesday.at(database_release_time).do(self.run_polling_window, attempts=20, interval_minutes=1)
        schedule.every().thursday.at(database_release_time).do(self.run_polling_window, attempts=20, interval_minutes=1)
        schedule.every().friday.at(database_release_time).do(self.run_polling_window, attempts=20, interval_minutes=1)
        utils.downloader_logger.info(f"Smart scheduler active: Polling weekdays at {database_release_time}.")

        # Schedule for every weekday morning to catch odd releases
        schedule.every().monday.at("08:00").do(self.run_polling_window, attempts=5, interval_minutes=5)
        schedule.every().tuesday.at("08:00").do(self.run_polling_window, attempts=5, interval_minutes=5)
        schedule.every().wednesday.at("08:00").do(self.run_polling_window, attempts=5, interval_minutes=5)
        schedule.every().thursday.at("08:00").do(self.run_polling_window, attempts=5, interval_minutes=5)
        schedule.every().friday.at("08:00").do(self.run_polling_window, attempts=5, interval_minutes=5)

        while True:
            schedule.run_pending()
            time.sleep(30)  # Check the schedule queue every 30 seconds

    def check_and_update_zip_files(self):
        """Check for updates, download new zip files if available, and send email notification for updated years."""
        updated_years = []

        for year in self.years:
            # Download zip file if we don't have it or there is a new timestamp on the server
            last_modified_time_on_server = self.get_last_modified(year)
            if last_modified_time_on_server is None:
                utils.downloader_logger.warning(f"Server did not return 'Last-Modified' header for {year}.zip, skipping...")
                continue
            try:
                server_file_date = datetime.strptime(last_modified_time_on_server, '%a, %d %b %Y %H:%M:%S %Z')
            except ValueError:
                utils.downloader_logger.error(f"Could not parse 'Last-Modified' server date for {year}.zip, skipping...")
                continue

            database_last_modified_time = self.cotDatabase.get_zipfile_last_modified_time(year)
            if database_last_modified_time:
                if server_file_date > database_last_modified_time:
                    utils.downloader_logger.info(f'Updating: {year}.zip')
                    url = self.url_prefix + f'{year}.zip'
                    self.download_and_extract_zip(url, year)
                    self.cotDatabase.update_zip_file(year, server_file_date)
                    updated_years.append(year)
                else:
                    utils.downloader_logger.info(f'No update needed for {year}.zip')
            else:
                utils.downloader_logger.info(f'Downloading: {year}.zip')
                url = self.url_prefix + f'{year}.zip'
                self.download_and_extract_zip(url, year)
                self.cotDatabase.update_zip_file(year, server_file_date)
                utils.downloader_logger.warning(f"Updated database {year}.zip, with new date: {server_file_date}")
                updated_years.append(year)

        if updated_years:
            utils.downloader_logger.info(f"Updated years: {', '.join(map(str, updated_years))}")
            if self.enable_email_notifications:
                self.send_email_notification(updated_years)
        else:
            utils.downloader_logger.info("No updates detected for any years.")

        return updated_years
