"""Desktop entry point. PyInstaller freezes this into MMCA.exe / MMCA.app.

Starts the Streamlit app on a free localhost port and opens the user's
browser. Nothing is exposed to the network: the server binds to 127.0.0.1.
Closing the console window (Windows) or quitting the app (Mac) stops it.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path


def _base_dir() -> Path:
    # Running from a PyInstaller bundle: files are unpacked to sys._MEIPASS.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def _free_port(preferred: int = 8501) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port available")


def main() -> None:
    base = _base_dir()
    app = base / "app" / "streamlit_app.py"
    sys.path.insert(0, str(base))
    os.chdir(base)  # so Streamlit finds .streamlit/config.toml

    from streamlit.web import cli as stcli

    port = _free_port()
    print(f"MMCA is running at http://localhost:{port}  (close this window to quit)")
    sys.argv = [
        "streamlit", "run", str(app),
        "--global.developmentMode=false",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=false",          # opens the browser
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
