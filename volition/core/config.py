"""Settings from the environment, and where the app's files live."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Read at call time so tests (and deploys) can point it elsewhere."""
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")


def allowed_hosts() -> list[str]:
    """Host headers the app answers to, from comma-separated ALLOWED_HOSTS ("*" allows any).

    Guards against DNS rebinding, where another site's domain is pointed at this machine.
    """
    hosts = os.environ.get("ALLOWED_HOSTS") or "127.0.0.1,localhost,[::1]"
    return [host.strip().lower() for host in hosts.split(",") if host.strip()]


def timezone() -> ZoneInfo:
    """The business's time zone, from TIMEZONE (an IANA name such as "Europe/London"): it decides what "today" is.

    Read at call time, like DATA_DIR. An unknown name raises ZoneInfoNotFoundError.
    """
    return ZoneInfo(os.environ.get("TIMEZONE") or "Europe/London")
