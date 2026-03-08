import asyncio
import re
import shutil
import sys

_process: asyncio.subprocess.Process | None = None
_tunnel_url: str | None = None
_drain_task: asyncio.Task | None = None


async def start_tunnel(local_port: int) -> str | None:
    """Start a Cloudflare quick tunnel pointing to the local port.

    Returns the public https URL, or None if cloudflared is not available.
    """
    global _process, _tunnel_url

    if _tunnel_url:
        return _tunnel_url

    if not shutil.which("cloudflared"):
        sys.stderr.write("Warning: cloudflared not found on PATH. Falling back to localhost URLs.\n")
        return None

    _process = await asyncio.create_subprocess_exec(
        "cloudflared", "tunnel", "--url", f"http://localhost:{local_port}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    url_pattern = re.compile(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)")

    # cloudflared prints the URL to stderr
    async def _read_until_url():
        global _tunnel_url
        assert _process and _process.stderr
        while True:
            line = await _process.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            sys.stderr.write(f"[cloudflared] {text}\n")
            m = url_pattern.search(text)
            if m:
                _tunnel_url = m.group(1)
                return _tunnel_url
        return None

    try:
        url = await asyncio.wait_for(_read_until_url(), timeout=30)
    except asyncio.TimeoutError:
        sys.stderr.write("Warning: timed out waiting for cloudflared tunnel URL.\n")
        await stop_tunnel()
        return None

    if url:
        global _drain_task
        sys.stderr.write(f"Tunnel active: {url}\n")
        # Continue draining stderr in background so the process doesn't block
        _drain_task = asyncio.create_task(_drain_stderr())
    return url


async def _drain_stderr():
    """Keep reading stderr so the subprocess doesn't block on a full pipe."""
    if not _process or not _process.stderr:
        return
    try:
        while True:
            line = await _process.stderr.readline()
            if not line:
                break
    except Exception:
        pass


async def stop_tunnel():
    """Kill the cloudflared subprocess."""
    global _process, _tunnel_url, _drain_task
    if _drain_task:
        _drain_task.cancel()
        try:
            await _drain_task
        except (asyncio.CancelledError, Exception):
            pass
        _drain_task = None
    if _process:
        try:
            _process.terminate()
            await asyncio.wait_for(_process.wait(), timeout=5)
        except Exception:
            try:
                _process.kill()
            except Exception:
                pass
        _process = None
    _tunnel_url = None


def get_tunnel_url() -> str | None:
    return _tunnel_url
