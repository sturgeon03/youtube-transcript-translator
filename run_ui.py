from __future__ import annotations

import argparse
import socket

import uvicorn

from youtube_transcript_translator.ui.webapp.app import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local web UI for the YouTube transcript translator.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind. Use 0.0.0.0 on the GPU PC for LAN access.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port for the web UI.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open a browser on the machine running the server.",
    )
    return parser.parse_args()


def resolve_lan_ip() -> str | None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if ip.startswith("127."):
            return None
        return ip
    except OSError:
        return None
    finally:
        probe.close()


def print_access_urls(host: str, port: int) -> None:
    print()
    print("Web UI server is starting.", flush=True)
    print(f"- Local URL: http://127.0.0.1:{port}", flush=True)
    if host in {"0.0.0.0", "::"}:
        lan_ip = resolve_lan_ip()
        if lan_ip:
            print(f"- LAN URL:   http://{lan_ip}:{port}", flush=True)
            print("  Open the LAN URL from the laptop browser.", flush=True)
        else:
            print("- LAN URL:   Could not detect the LAN IP automatically.", flush=True)
    print()


def main() -> None:
    args = parse_args()
    app = create_app(open_browser=not args.no_browser and args.host == "127.0.0.1")
    print_access_urls(args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
