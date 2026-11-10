"""Environment and credential loading.

Configuration is loaded lazily so importing the package never requires API
keys and never creates directories.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from . import paths
from .errors import ConfigurationError

_LOADED = False


def get_env_file() -> Path:
    """Return the .env file used by the application.

    ``CONSENSUS_ENV_FILE`` wins.  Source checkouts use the project root;
    installed packages use the per-user config directory.
    """

    override = os.environ.get("CONSENSUS_ENV_FILE")
    if override:
        return Path(override).expanduser()

    if paths.is_source_checkout():
        return paths.SOURCE_ROOT / ".env"

    return paths.user_config_dir() / ".env"


def load_environment() -> None:
    """Load the configured .env file once, without overriding real env vars."""

    global _LOADED

    if _LOADED:
        return

    env_file = get_env_file()
    if env_file.is_file():
        load_dotenv(env_file, override=False)

    _LOADED = True


def get_required_env(name: str) -> str:
    """Return a required environment variable or raise a safe error."""

    load_environment()
    value = os.getenv(name)

    if not value:
        raise ConfigurationError(
            f"{name} is not set. Add it to {get_env_file()} or export it."
        )

    return value
