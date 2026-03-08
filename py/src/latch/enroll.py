import asyncio
import sys
import webbrowser

from .approval import get_approval_server
from .tunnel import start_tunnel, stop_tunnel


async def _run(remote: bool = False):
    server = await get_approval_server()

    if remote:
        tunnel_url = await start_tunnel(server.port)
        if tunnel_url:
            url = f"{tunnel_url}/enroll"
            sys.stderr.write(f"Open on your phone: {url}\n")
        else:
            sys.stderr.write("Warning: could not start tunnel. Falling back to local enrollment.\n")
            remote = False

    if not remote:
        url = f"http://localhost:{server.port}/enroll"
        sys.stderr.write(f"Opening enrollment page: {url}\n")
        webbrowser.open(url)

    # Wait for enrollment to complete via event (set by _post_enroll_verify)
    server._enroll_complete = asyncio.Event()
    await server._enroll_complete.wait()
    await asyncio.sleep(0.5)
    sys.stderr.write("Enrollment complete.\n")
    await server.stop()
    if remote:
        await stop_tunnel()


def main(remote: bool = False):
    asyncio.run(_run(remote=remote))
