import { css } from "lit";

export const theme = css`
  :host {
    --bg: #0d1117;
    --card-bg: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --blue: #58a6ff;
    --green: #238636;
    --green-bright: #3fb950;
    --red: #da3633;
    --red-bright: #f85149;
    --font-mono: "SF Mono", "Fira Code", monospace;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      sans-serif;

    font-family: var(--font-sans);
    color: var(--text);
  }
`;
