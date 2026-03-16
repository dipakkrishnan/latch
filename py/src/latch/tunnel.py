import asyncio
import os
import shutil
import sys

_process: asyncio.subprocess.Process | None = None
_tunnel_url: str | None = None
_drain_task: asyncio.Task | None = None

# Named tunnel config — set via env vars, provisioned by `latch setup` wizard
CLOUDFLARE_TUNNEL_ID = os.environ.get("CLOUDFLARE_TUNNEL_ID", "")
CLOUDFLARE_TUNNEL_HOSTNAME = os.environ.get("CLOUDFLARE_TUNNEL_HOSTNAME", "")
CLOUDFLARE_TUNNEL_CRED_FILE = os.environ.get("CLOUDFLARE_TUNNEL_CRED_FILE", "")


async def start_tunnel(local_port: int) -> str | None:
    """Start the named Cloudflare tunnel pointing to the local port.

    Returns the public https URL, or None if not configured or cloudflared is missing.
    """
    global _process, _tunnel_url, _drain_task

    if _tunnel_url:
        return _tunnel_url

    if not CLOUDFLARE_TUNNEL_ID or not CLOUDFLARE_TUNNEL_HOSTNAME:
        sys.stderr.write("No tunnel configured (set CLOUDFLARE_TUNNEL_ID/HOSTNAME or run `latch setup`).\n")
        return None

    if not shutil.which("cloudflared"):
        sys.stderr.write("Warning: cloudflared not found on PATH. No tunnel available.\n")
        return None

    args = ["cloudflared", "tunnel"]
    if CLOUDFLARE_TUNNEL_CRED_FILE:
        args += ["--credentials-file", CLOUDFLARE_TUNNEL_CRED_FILE, "--origincert", ""]
    args += ["--url", f"http://localhost:{local_port}", "run", CLOUDFLARE_TUNNEL_ID]

    _process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _wait_for_ready():
        global _tunnel_url
        assert _process and _process.stderr
        while True:
            line = await _process.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            sys.stderr.write(f"[cloudflared] {text}\n")
            if "Registered tunnel connection" in text:
                _tunnel_url = f"https://{CLOUDFLARE_TUNNEL_HOSTNAME}"
                return _tunnel_url
        return None

    try:
        url = await asyncio.wait_for(_wait_for_ready(), timeout=30)
    except asyncio.TimeoutError:
        sys.stderr.write("Warning: timed out waiting for tunnel to register.\n")
        await stop_tunnel()
        return None

    if url:
        sys.stderr.write(f"Tunnel active: {url}\n")
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
