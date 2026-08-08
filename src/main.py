import logging
import multiprocessing
import os
import signal
import sys
import threading
import time

import cotmetrics.utils as utils

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

STORE_POLL_SECONDS = 5 * 60


def store_poll_loop():
    """Notice a new COT week even when nobody has the site open.

    A THREAD, deliberately, where daily_options_update_scheduler below is a
    multiprocessing.Process. That one only has to fetch options snapshots and write
    them out, so it does not care which process it runs in. This one mutates the
    CotIndexer singleton that serves HTTP requests, and a child process would refresh
    its own forked copy while the web process kept serving the previous week. Same
    call, wrong address space.

    The navbar callback polls the same way and is the primary trigger, but dcc.Interval
    is client-side: it only ticks while a browser tab is open. Without this loop the
    first visitor after a release pays the ~90 second rebuild. With it, an unattended
    app is current before anyone arrives.

    Every 5 minutes, always, rather than a window around the Friday release. The store
    is a replica fed by a producer push, so it can advance at times no schedule here
    predicts (revisions, a backfill, a manual run, a late release). The check itself is
    one small JSON read, so a window would buy nothing and could only be wrong.
    """
    from cotmetrics.indexer import get_indexer

    utils.cot_logger.info(f"Store poller started (every {STORE_POLL_SECONDS}s).")
    while True:
        time.sleep(STORE_POLL_SECONDS)
        try:
            if get_indexer().refresh_if_stale():
                utils.cot_logger.info("Store poller: picked up a new COT week.")
        except Exception as e:
            # Never let a transient read kill the loop. A poller that dies silently
            # is worse than no poller, because the navbar still looks like it is
            # watching. Log and wait for the next tick.
            utils.cot_logger.error(f"Store poller failed, will retry: {e}")


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

    # Check if we are in the Werkzeug reloader child process
    is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

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
                options_update_process = multiprocessing.Process(
                    target=daily_options_update_scheduler
                )
                options_update_process.start()
            else:
                utils.cot_logger.info("[FAST BOOT] Skipping background schedulers.")
                options_update_process = None

            # Started even under --fast, unlike the options scheduler above. --fast
            # buys a faster BOOT, and this costs nothing at boot: it sleeps first and
            # then does one small JSON read every 5 minutes. Skipping it would hand a
            # --fast run the stale-data bug this exists to close.
            threading.Thread(
                target=store_poll_loop, name="store-poller", daemon=True
            ).start()

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
                if options_update_process:
                    options_update_process.terminate()
                    options_update_process.join()
