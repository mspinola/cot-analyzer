import logging
import multiprocessing
import os
import signal
import sys

from CotDataDownloader import CotDataDownloader
from CotCmrIndexer import CotCmrIndexer
from CotDatabase import CotDatabase

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    cotDownloader = CotDataDownloader()
    cotDownloader.check_and_update_zip_files()
    port = os.getenv('PORT', '5001')

    enable_server = True
    if not enable_server:
        cmrIndexer = CotCmrIndexer()
    else:
        # Start the background process for hourly zip updates
        from app_cot import app

        cot_data_update_process = multiprocessing.Process(target=cotDownloader.check_zip_updates)
        cot_data_update_process.start()

        try:
            app.run(host="0.0.0.0", port=port, debug=False)
        except KeyboardInterrupt:
            print("Keyboard interrupt received, terminating background update process...")
        finally:
            cot_data_update_process.terminate()
            cot_data_update_process.join()
