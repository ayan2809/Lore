"""Run a real FalkorDB on this machine without Docker, using FalkorDBLite (embedded server).

    make db-lite          # or: uv run --no-project --python 3.12 --with falkordblite \
                          #         python scripts/falkordb_lite.py
    then in another terminal: LORE_FALKORDB_PORT=6390 make load-fake

It starts the same FalkorDB module (4.18.x when this was written) behind a local Redis server
on port 6390 and keeps it running until you press Ctrl+C. Data is saved in .falkordb-lite/.
Dev-only: there is no Browser UI on port 3000; use Docker for that (see docs/RUNBOOK.md).
"""

import signal
import sys
import time
from pathlib import Path

from redislite.falkordb_client import FalkorDB

PORT = sys.argv[1] if len(sys.argv) > 1 else "6390"
DATA = Path(__file__).resolve().parent.parent / ".falkordb-lite"
DATA.mkdir(exist_ok=True)

db = FalkorDB(str(DATA / "lore.db"), serverconfig={"port": PORT})
print(f"FalkorDB (lite) listening on localhost:{PORT}. Ctrl+C to stop.", flush=True)
# Treat `kill` like Ctrl+C, so redislite's exit hook stops the server instead of orphaning it.
signal.signal(signal.SIGTERM, signal.default_int_handler)
try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    pass  # redislite shuts the server down (and saves) on exit
