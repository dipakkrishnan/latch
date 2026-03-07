import yaml

from .config import CONFIG_DIR

_PATH = CONFIG_DIR / "servers.yaml"
DEFAULT_SERVERS = "servers: []\n"
_cache = None


def _validate_servers_config(config):
    if not isinstance(config, dict):
        raise ValueError("servers.yaml must be a mapping with key 'servers'")
    servers = config.get("servers")
    if servers is None:
        config["servers"] = []
        servers = config["servers"]
    if not isinstance(servers, list):
        raise ValueError("'servers' must be a list")
    for idx, server in enumerate(servers):
        if not isinstance(server, dict):
            raise ValueError(f"servers[{idx}] must be a mapping")
        alias = server.get("alias")
        command = server.get("command")
        args = server.get("args", [])
        env = server.get("env")
        if not isinstance(alias, str) or not alias.strip() or any(c.isspace() for c in alias):
            raise ValueError(f"servers[{idx}].alias must be a non-empty string without whitespace")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"servers[{idx}].command must be a non-empty string")
        if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
            raise ValueError(f"servers[{idx}].args must be a list of strings")
        if env is not None:
            if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
                raise ValueError(f"servers[{idx}].env must be a mapping of string keys/values")
    return config


def load_servers(force=False):
    global _cache
    if _cache and not force:
        return _cache
    if not _PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(DEFAULT_SERVERS)
    parsed = yaml.safe_load(_PATH.read_text()) or {"servers": []}
    _cache = _validate_servers_config(parsed)
    return _cache


def save_servers(config):
    global _cache
    parsed = _validate_servers_config(config)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(yaml.safe_dump(parsed, sort_keys=False))
    _cache = parsed


def upsert_server(alias, command, args=None, env=None):
    alias = (alias or "").strip()
    command = (command or "").strip()
    args = list(args or [])
    if not alias or any(c.isspace() for c in alias):
        raise ValueError("alias must be non-empty and contain no whitespace")
    if not command:
        raise ValueError("command must be non-empty")
    if any(not isinstance(a, str) for a in args):
        raise ValueError("args must be strings")
    if env is not None and any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
        raise ValueError("env must contain string keys and values")

    config = load_servers(force=True)
    servers = config["servers"]
    new_server = {"alias": alias, "command": command, "args": args}
    if env:
        new_server["env"] = env

    for i, s in enumerate(servers):
        if s.get("alias") == alias:
            servers[i] = new_server
            save_servers(config)
            return "updated"

    servers.append(new_server)
    save_servers(config)
    return "added"


def delete_server(alias):
    config = load_servers(force=True)
    servers = config["servers"]
    next_servers = [s for s in servers if s.get("alias") != alias]
    if len(next_servers) == len(servers):
        return False
    config["servers"] = next_servers
    save_servers(config)
    return True

