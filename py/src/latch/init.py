import json

from .config import CONFIG_DIR
from .policy import DEFAULT_POLICY


def init(config_dir=None, force=False):
    d = config_dir or CONFIG_DIR
    d.mkdir(parents=True, exist_ok=True)
    created = []

    files = {
        "policy.yaml": DEFAULT_POLICY,
        "credentials.json": json.dumps([], indent=2),
        "audit.jsonl": "",
        "servers.yaml": "servers: []\n",
    }

    for name, content in files.items():
        path = d / name
        if path.exists() and not force:
            print(f"  exists: {path}")
        else:
            path.write_text(content)
            created.append(name)
            print(f"  created: {path}")

    if created:
        print(f"\nInitialized latch config at {d} ({len(created)} file(s) created)")
    else:
        print(f"\nLatch config already initialized at {d}")
