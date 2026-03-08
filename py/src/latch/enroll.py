import asyncio
import sys
import webbrowser

from . import credentials
from .approval import get_approval_server
from .tunnel import start_tunnel, stop_tunnel


async def _run(remote: bool = False):
    server = await get_approval_server()

    if remote:
        tunnel_url = await start_tunnel(server.port)
        if tunnel_url:
            server.set_tunnel_url(tunnel_url)
            url = f"{tunnel_url}/enroll"
            sys.stderr.write(f"Open on your phone: {url}\n")
        else:
            sys.stderr.write("Warning: could not start tunnel. Falling back to local enrollment.\n")
            url = f"http://localhost:{server.port}/enroll"
            sys.stderr.write(f"Opening enrollment page: {url}\n")
            webbrowser.open(url)
    else:
        url = f"http://localhost:{server.port}/enroll"
        sys.stderr.write(f"Opening enrollment page: {url}\n")
        webbrowser.open(url)

    # Wait until a credential is saved (poll), then shut down
    initial_count = len(credentials.load())
    while len(credentials.load()) == initial_count:
        await asyncio.sleep(0.5)
    await asyncio.sleep(1)
    sys.stderr.write("Enrollment complete.\n")
    await server.stop()
    if remote:
        await stop_tunnel()


def main(remote: bool = False):
    asyncio.run(_run(remote=remote))
