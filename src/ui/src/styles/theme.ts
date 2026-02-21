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
    --font-mono: "SF Mono", "JetBrains Mono", "Fira Code", monospace;
    --font-sans: "Avenir Next", "IBM Plex Sans", "Segoe UI", sans-serif;
    --radius: 14px;

    font-family: var(--font-sans);
    color: var(--text);
  }
`;
