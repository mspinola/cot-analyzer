import logging
import multiprocessing
import os
import signal
import sys
import time

import cotmetrics.utils as utils
from cotmetrics.pipelines.etl_scheduler import CotJobScheduler

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


class NoDashComponentFilter(logging.Filter):
    def filter(self, record):
        # Returns False if the string is in the log message, which drops the log
        return "_dash-update-component" not in record.getMessage()


# Create a filter that drops any log record containing ".map"
class SuppressSourceMapErrors(logging.Filter):
    def filter(self, record):
        # Return False (drop the log) if the message contains a request for a .map file
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            if ".map" in str(exc_value):
                return False
        return ".map" not in record.getMessage()

# If you are also using Werkzeug's default logger, filter that too
logging.getLogger('werkzeug').addFilter(SuppressSourceMapErrors())

# Apply filter to the werkzeug logger
log = logging.getLogger('werkzeug')
log.addFilter(NoDashComponentFilter())
log.addFilter(SuppressSourceMapErrors())

def daily_options_update_scheduler():
    import datetime

    import pytz
    from cotmetrics.options_data import update_all_daily_options
    eastern = pytz.timezone('US/Eastern')

    utils.cot_logger.info("Daily options and price update scheduler started.")

    while True:
        now = datetime.datetime.now(eastern)

        # Determine if we are currently inside the overnight update window (6:00 PM - 6:00 AM)
        is_in_update_window = (now.hour >= 18 or now.hour < 6)

        if is_in_update_window:
            utils.cot_logger.info("Scheduler inside update window. Triggering options snapshot refresh...")
            try:
                # Prices now come from the cotdata store (Norgate producer via cotdata-update);
                # only the options Max Pain snapshots are refreshed here.
                update_all_daily_options()

                utils.cot_logger.info("Options snapshot refresh completed successfully.")
            except Exception as e:
                utils.cot_logger.error(f"Scheduled update failed: {e}")

            # Sleep for 3 hours before checking/polling again
            sleep_seconds = 3 * 3600
        else:
            # We are in the daytime. Calculate seconds until the next window starts (6:00 PM ET today)
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            sleep_seconds = (target - now).total_seconds()
            utils.cot_logger.info(f"Daytime mode. Sleeping for {sleep_seconds:.0f} seconds until update window starts at 6:00 PM ET.")

        time.sleep(sleep_seconds)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="COT Analyzer")
    parser.add_argument("--debug", action="store_true", help="Launch in debug mode (enables Dash debug server)")
    parser.add_argument("--fast", action="store_true", help="Skip data checks and updates on boot for faster startup")
    args, unknown = parser.parse_known_args()

    dash_debug = False
    if args.debug:
        utils.cot_logger.warning("Running in DEBUG mode.")
        dash_debug = True

    cotDownloader = CotJobScheduler()

    # Check if we are in the Werkzeug reloader child process
    is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    if not is_reloader:
        # Trigger an initial ETL check if needed (only in the main parent process)
        cotDownloader.run_polling_window(attempts=1, interval_minutes=1, force_disable_email=True)

        if not os.path.exists('data/raw_cot_data.parquet'):
            utils.cot_logger.warning("raw_cot_data.parquet not found! Forcing ETL pipeline to generate it...")
            import importlib
            etl_module = importlib.import_module("cotmetrics.pipelines.01_etl_downloader")
            etl_module.run_etl_pipeline()

    enable_server = True
    if not enable_server:
        utils.cot_logger.warning(
            "Server is disabled. Only running CotIndexer initialization.")
        from cotmetrics.CotIndexer import CotIndexer
        cmrIndexer = CotIndexer()
        from cotmetrics.indexer import boot_options_update
        boot_options_update()
    else:
        if not is_reloader:
            if not getattr(args, 'fast', False):
                # Guarantee daily price and options cache validation on boot to prevent UI blocking
                utils.cot_logger.info("Eagerly validating options cache on boot (prices come from the cotdata store)...")
                from cotmetrics.indexer import boot_options_update
                boot_options_update()
            else:
                utils.cot_logger.info("[FAST BOOT] Skipping eager cache validation.")

            if not getattr(args, 'fast', False):
                # Start the background process for hourly zip updates
                cot_data_update_process = multiprocessing.Process(
                    target=cotDownloader.start_scheduler
                )
                cot_data_update_process.start()

                options_update_process = multiprocessing.Process(
                    target=daily_options_update_scheduler
                )
                options_update_process.start()
            else:
                utils.cot_logger.info("[FAST BOOT] Skipping background schedulers.")
                cot_data_update_process = None
                options_update_process = None

        from app_cot import app

        try:
            start_time = time.time()
            port = os.getenv('PORT', '5001')
            app.run(host="0.0.0.0", port=port, debug=dash_debug)
            utils.cot_logger.info(f"app.run took: {time.time() - start_time:.2f}s")
        except KeyboardInterrupt:
            utils.cot_logger.warning(
                "Keyboard interrupt received, terminating background update processes...")
        finally:
            if not is_reloader:
                if cot_data_update_process:
                    cot_data_update_process.terminate()
                    cot_data_update_process.join()
                if options_update_process:
                    options_update_process.terminate()
                    options_update_process.join()
