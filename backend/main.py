import socket
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings


def _is_port_available(host: str, port: int) -> bool:
    probe_host = "0.0.0.0" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, port))
        except OSError:
            return False
    return True


def main() -> None:
    settings = get_settings()
    if not _is_port_available(settings.host, settings.port):
        raise SystemExit(
            f"Port {settings.port} is already in use. "
            f"Change YUNXUN_PORT or PORT in the environment, then start the backend again."
        )

    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
