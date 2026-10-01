"""Settings from the environment, and where the app's files live."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Read at call time so tests (and deploys) can point it elsewhere."""
    return Path(os.environ.get("DATA_DIR") or ROOT / "data")


def allowed_hosts() -> list[str]:
    """Host headers the app answers to, from comma-separated ALLOWED_HOSTS ("*" allows any).

    Guards against DNS rebinding, where another site's domain is pointed at this machine.
    """
    hosts = os.environ.get("ALLOWED_HOSTS") or "127.0.0.1,localhost,[::1]"
    return [host.strip().lower() for host in hosts.split(",") if host.strip()]
