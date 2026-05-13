import logging
import time
import utils

from CotDatabase import CotDatabase

# Instantiate once here
start_time = time.time()
cotDatabase = CotDatabase()
utils.cot_logger.info(f"CotDatabase took: {time.time() - start_time:.2f}s")
