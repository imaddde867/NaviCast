"""Isolate service imports from developer credentials and platform log paths."""
import os
import tempfile
from pathlib import Path

os.environ['NAVICAST_MODE'] = 'demo'
os.environ['NAVICAST_DB_PASSWORD'] = 'test-only'
os.environ['NAVICAST_LOG_DIR'] = str(Path(tempfile.gettempdir()) / 'navicast-test-logs')
