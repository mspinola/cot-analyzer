import logging
import time

from CotCmrIndexer import CotCmrIndexer

# Instantiate once here
# Note, this is a slow operation, so we only want to do it once and pass the indexer around as needed.
print("Loading COT Data... (this might take a moment)")
start_time = time.time()
cotIndexer = CotCmrIndexer()
logging.info(f"Loading COT data took: {time.time() - start_time:.2f}s")
