#!/usr/bin/python3
"""DNS-over-WebSocket bridge for wasm mail clients (Velta C3).

The wasm core resolves hostnames through the proxy's /dns/{host} endpoint
(patch 0007): it opens a WebSocket and expects the FIRST text message to be
a JSON array of IP-address strings, after which the server may close.

nginx ignores that address and dials this relay's own IMAP/SMTP. Answer
127.0.0.1 for the mail domain (argv[1]) so a proxied name does not send the
client after the public anycast addresses. Other names get an empty list.
"""
import asyncio
import sys
from urllib.parse import unquote

from websockets.server import serve

ALLOWED_SUFFIX = sys.argv[1] if len(sys.argv) > 1 else ""


def answer(host):
    allowed = bool(host) and (
        host == ALLOWED_SUFFIX or host.endswith("." + ALLOWED_SUFFIX)
    )
    return '["127.0.0.1"]' if allowed else "[]"


async def handle(ws):
    req = getattr(ws, "request", ws)
    host = unquote(req.path).rsplit("/", 1)[-1].strip()
    await ws.send(answer(host))


async def main():
    async with serve(handle, "127.0.0.1", 8153, max_size=64, ping_interval=None):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
