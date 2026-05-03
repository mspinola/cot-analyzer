import logging
import time

from CotDatabase import CotDatabase

# Instantiate once here
start_time = time.time()
cotDatabase = CotDatabase()
logging.info(f"CotDatabase took: {time.time() - start_time:.2f}s")
