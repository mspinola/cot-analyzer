import logging
import os
import requests
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

# Ensure directories exist
log_file_name = "log/cot_downloader.log"
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
    def __init__(self, data_dir='data/cot_data', xls_data_dir='data/xls_data', send_email=False):
        self.data_dir = data_dir
        self.xls_data_dir = xls_data_dir
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
        with open("config/params.yaml", 'r') as yf:
            yaml_data = yaml.safe_load(yf)
            for year in yaml_data["years"]:
                self.years.append(year)

    def check_zip_updates(self, sleep_interval=3600):
        """Check for zip updates every hour."""
        while True:
            logging.info("Starting the zip file update check.")
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
                    print(f"Could not delete {new_file_path}: {e}")
                    return

            try:
                shutil.move(extracted_file_path, new_file_path)
                print(f"Renamed extracted file to: {new_file_path}")
            except PermissionError as e:
                print(f"Error renaming file {extracted_file_path} to {new_file_path}: {e}")

    def send_email_notification(self, updated_years):
        """Send an email notification listing the years with new files downloaded."""
        sender_email = os.environ.get("EMAIL_USER")
        receiver_email = os.environ.get("EMAIL_USER")
        password = os.environ.get("EMAIL_PASSWORD")
        print(receiver_email, password)

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
            logging.info(f"Email notification successfully sent for updated years: {', '.join(map(str, updated_years))}")
        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")

    def check_and_update_zip_files(self):
        """Check for updates, download new zip files if available, and send email notification for updated years."""
        updated_years = []

        for year in self.years:
            # Download zip file if we don't have it or there is a new timestamp on the server
            last_modified = self.get_last_modified(year)
            if last_modified is None:
                logging.warning(f"No 'Last-Modified' header for {year}.zip, skipping...")
                continue
            try:
                current_date = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S %Z')
            except ValueError:
                logging.error(f"Could not parse 'Last-Modified' date for {year}.zip, skipping...")
                continue

            zipfile_last_modified = self.cotDatabase.get_zipfile_last_modified_time(year)
            if zipfile_last_modified:
                if current_date > zipfile_last_modified:
                    logging.info(f'Updating: {year}.zip')
                    url = self.url_prefix + f'{year}.zip'
                    self.download_and_extract_zip(url, year)
                    self.cotDatabase.update_zip_file(year, zipfile_last_modified)
                    updated_years.append(year)
                else:
                    logging.info(f'No update needed for {year}.zip')
            else:
                logging.info(f'Downloading: {year}.zip')
                url = self.url_prefix + f'{year}.zip'
                self.download_and_extract_zip(url, year)
                self.cotDatabase.update_zip_file(year, last_modified)
                updated_years.append(year)

        if updated_years:
            logging.info(f"Updated years: {', '.join(map(str, updated_years))}")
            if self.enable_email_notifications:
                self.send_email_notification(updated_years)
        else:
            logging.info("No updates detected for any years.")
