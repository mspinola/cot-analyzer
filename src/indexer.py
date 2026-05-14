import logging
import time
import utils

from CotIndexer import CotIndexer

# Instantiate once here
# Note, this is a slow operation, so we only want to do it once and pass the indexer around as needed.
print("Loading COT Data... (this might take a moment)")
start_time = time.time()
cotIndexer = CotIndexer()
utils.cot_logger.info(f"Loading COT data took: {time.time() - start_time:.2f}s")
