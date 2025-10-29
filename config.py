"""Shared configuration helpers for NAVICAST services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

# Default values reflect original hard-coded settings
_DEFAULT_DB_CONFIG = {
    "dbname": "ais_project",
    "user": "postgres",
    "password": "120705imad",
    "host": "localhost",
    "port": "5432",
}

_LOG_DIR_ENV_KEY = "NAVICAST_LOG_DIR"


def get_db_config() -> Dict[str, str]:
    """Return database connection configuration, allowing environment overrides."""
    return {
        "dbname": os.getenv("NAVICAST_DB_NAME", _DEFAULT_DB_CONFIG["dbname"]),
        "user": os.getenv("NAVICAST_DB_USER", _DEFAULT_DB_CONFIG["user"]),
        "password": os.getenv("NAVICAST_DB_PASSWORD", _DEFAULT_DB_CONFIG["password"]),
        "host": os.getenv("NAVICAST_DB_HOST", _DEFAULT_DB_CONFIG["host"]),
        "port": os.getenv("NAVICAST_DB_PORT", _DEFAULT_DB_CONFIG["port"]),
    }


def ensure_log_dir() -> Path:
    """Create (if needed) and return the directory used for log files."""
    log_dir = Path(os.getenv(_LOG_DIR_ENV_KEY, "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir
