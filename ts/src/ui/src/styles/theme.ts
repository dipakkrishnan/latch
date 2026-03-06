import { css } from "lit";

export const theme = css`
  :host {
    --bg: #0d1117;
    --card-bg: #161b22;
    --card-soft: #1f2630;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --blue: #58a6ff;
    --blue-soft: #7bb5ff;
    --green: #238636;
    --green-bright: #3fb950;
    --red: #da3633;
    --red-bright: #f85149;
    --amber: #d29922;
    --purple: #a371f7;
    --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", monospace;
    --font-sans: "Avenir Next", "IBM Plex Sans", "Segoe UI", sans-serif;
    --radius: 14px;
    --transition: 0.15s ease;

    font-family: var(--font-sans);
    color: var(--text);
  }
`;

/* Semantic color mapping for actions */
export const actionColors: Record<string, { color: string; border: string }> = {
  allow: { color: "var(--green-bright)", border: "color-mix(in srgb, var(--green) 70%, var(--border))" },
  ask: { color: "var(--amber)", border: "color-mix(in srgb, var(--amber) 50%, var(--border))" },
  deny: { color: "var(--red-bright)", border: "color-mix(in srgb, var(--red) 70%, var(--border))" },
  browser: { color: "var(--blue-soft)", border: "color-mix(in srgb, var(--blue) 55%, var(--border))" },
  webauthn: { color: "var(--purple)", border: "color-mix(in srgb, var(--purple) 55%, var(--border))" },
};

export const sharedStyles = css`
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 54px;
    padding: 0.18rem 0.52rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border: 1px solid var(--border);
    transition: border-color var(--transition), color var(--transition), background var(--transition);
  }
  .badge-allow {
    color: var(--green-bright);
    border-color: color-mix(in srgb, var(--green) 70%, var(--border));
  }
  .badge-ask {
    color: var(--amber);
    border-color: color-mix(in srgb, var(--amber) 50%, var(--border));
  }
  .badge-deny {
    color: var(--red-bright);
    border-color: color-mix(in srgb, var(--red) 70%, var(--border));
  }
  .badge-browser {
    color: var(--blue-soft);
    border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
  }
  .badge-webauthn {
    color: var(--purple);
    border-color: color-mix(in srgb, var(--purple) 55%, var(--border));
  }
  .card {
    border: 1px solid var(--border);
    background: linear-gradient(
      180deg,
      color-mix(in srgb, var(--card-bg) 90%, white),
      var(--card-bg)
    );
    border-radius: var(--radius);
    padding: 0.8rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  }
  .btn {
    border-radius: 10px;
    border: 1px solid var(--border);
    padding: 0.43rem 0.74rem;
    font-weight: 600;
    font-size: 0.82rem;
    cursor: pointer;
    transition: all var(--transition);
  }
  .btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .btn-primary {
    background: var(--blue);
    border-color: color-mix(in srgb, var(--blue) 70%, #fff);
    color: #071527;
  }
  .btn-danger {
    background: transparent;
    color: var(--text-muted);
  }
  .btn-danger:hover {
    background: color-mix(in srgb, var(--red) 40%, transparent);
    border-color: var(--red);
    color: #fff;
  }
  .btn-ghost {
    background: transparent;
    color: var(--text);
  }
  .btn-ghost:hover {
    background: rgba(88, 166, 255, 0.08);
    border-color: color-mix(in srgb, var(--blue) 40%, var(--border));
  }
  .icon-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.3rem;
    min-height: 22px;
    padding: 0.16rem 0.46rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    color: var(--text-muted);
    background: color-mix(in srgb, var(--card-bg) 82%, black);
    font-size: 0.72rem;
    font-weight: 600;
    line-height: 1;
  }
  .status-dot {
    width: 0.48rem;
    height: 0.48rem;
    border-radius: 999px;
    display: inline-block;
    background: var(--green-bright);
    box-shadow: 0 0 0 2px rgba(63, 185, 80, 0.18);
  }
  .segmented {
    display: inline-flex;
    gap: 0.28rem;
    padding: 0.22rem;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--card-bg) 85%, black);
  }
  .segmented button {
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0.34rem 0.58rem;
    font-size: 0.75rem;
    font-weight: 650;
    letter-spacing: 0.02em;
    text-transform: lowercase;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition: all var(--transition);
  }
  .segmented button:hover {
    color: var(--text);
    border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
    background: rgba(88, 166, 255, 0.08);
  }
  .segmented button.active {
    color: var(--text);
    background: rgba(88, 166, 255, 0.16);
    border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
  }
  .segmented button.action-allow.active {
    color: #d5ffe0;
    background: color-mix(in srgb, var(--green) 35%, transparent);
    border-color: color-mix(in srgb, var(--green) 65%, var(--border));
  }
  .segmented button.action-ask.active {
    color: #ffe9bf;
    background: color-mix(in srgb, var(--amber) 30%, transparent);
    border-color: color-mix(in srgb, var(--amber) 55%, var(--border));
  }
  .segmented button.action-deny.active {
    color: #ffd8d6;
    background: color-mix(in srgb, var(--red) 30%, transparent);
    border-color: color-mix(in srgb, var(--red) 65%, var(--border));
  }
  .segmented button.action-browser.active {
    color: #d8ebff;
    background: color-mix(in srgb, var(--blue) 30%, transparent);
    border-color: color-mix(in srgb, var(--blue) 60%, var(--border));
  }
  .segmented button.action-webauthn.active {
    color: #ecdfff;
    background: color-mix(in srgb, var(--purple) 35%, transparent);
    border-color: color-mix(in srgb, var(--purple) 60%, var(--border));
  }
`;

export function relativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const now = Date.now();
  const diff = now - date.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}
