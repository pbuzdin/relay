#!/usr/bin/python3
"""DNS-over-WebSocket bridge for wasm mail clients (Velta C3).

The wasm core resolves hostnames through the proxy's /dns/{host} endpoint
(patch 0007): it opens a WebSocket and expects the FIRST text message to be
a JSON array of IP-address strings, after which the server may close.

This bridge answers with the system resolver's view of {host}, restricted
to the relay's own mail domain (passed as argv[1]) so the endpoint cannot
be abused as an open resolver.
"""
import asyncio
import json
import socket
import sys
from urllib.parse import unquote

from websockets.server import serve

ALLOWED_SUFFIX = sys.argv[1] if len(sys.argv) > 1 else ""


async def resolve_host(host):
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    ips = []
    for family, _type, _proto, _canonname, sockaddr in infos:
        ip = sockaddr[0]
        if family == socket.AF_INET6:
            ip = ip.split("%")[0]
        if ip not in ips:
            ips.append(ip)
    return ips


async def handle(ws):
    req = getattr(ws, "request", ws)
    path = unquote(req.path)
    host = path.rsplit("/", 1)[-1].strip()
    allowed = host and (
        host == ALLOWED_SUFFIX or host.endswith("." + ALLOWED_SUFFIX)
    )
    if not allowed:
        await ws.send("[]")
        return
    await ws.send(json.dumps(await resolve_host(host)))


async def main():
    async with serve(handle, "127.0.0.1", 8153, max_size=64, ping_interval=None):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
