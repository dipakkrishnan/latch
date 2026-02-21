import { LitElement, html, css } from "lit";
import { customElement, property } from "lit/decorators.js";
import { theme } from "../styles/theme.js";

@customElement("nav-bar")
export class NavBar extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
        width: 200px;
        min-height: 100vh;
        background: var(--card-bg);
        border-right: 1px solid var(--border);
        padding: 1.5rem 0;
      }
      .brand {
        font-size: 1rem;
        font-weight: 700;
        padding: 0 1.25rem 1.25rem;
        border-bottom: 1px solid var(--border);
        margin-bottom: 0.75rem;
        font-family: var(--font-mono);
        color: var(--blue);
      }
      a {
        display: block;
        padding: 0.6rem 1.25rem;
        text-decoration: none;
        color: var(--text-muted);
        font-size: 0.9rem;
        transition: color 0.15s, background 0.15s;
      }
      a:hover {
        color: var(--text);
        background: rgba(88, 166, 255, 0.08);
      }
      a.active {
        color: var(--blue);
        background: rgba(88, 166, 255, 0.12);
        border-left: 3px solid var(--blue);
        padding-left: calc(1.25rem - 3px);
      }
    `,
  ];

  @property({ type: String }) active = "policy";

  render() {
    const links = [
      { route: "policy", label: "Policy Rules" },
      { route: "credentials", label: "Credentials" },
      { route: "audit", label: "Audit Log" },
    ];

    return html`
      <div class="brand">agent-2fa</div>
      ${links.map(
        (l) => html`
          <a
            href="#/${l.route}"
            class=${this.active === l.route ? "active" : ""}
          >
            ${l.label}
          </a>
        `,
      )}
    `;
  }
}
