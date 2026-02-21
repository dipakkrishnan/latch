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
      }
      nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
      }
      .brand {
        font-size: 0.95rem;
        font-weight: 700;
        font-family: var(--font-mono);
        color: var(--blue-soft);
        letter-spacing: 0.02em;
      }
      .tabs {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.28rem;
        border-radius: 999px;
        background: color-mix(in srgb, var(--card-bg) 85%, black);
        border: 1px solid var(--border);
      }
      a {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
        min-width: 124px;
        border-radius: 999px;
        padding: 0.5rem 0.85rem;
        text-decoration: none;
        color: var(--text-muted);
        font-size: 0.85rem;
        font-weight: 600;
        transition: color 0.15s, background 0.15s, transform 0.15s;
      }
      a:hover {
        color: var(--text);
        background: rgba(88, 166, 255, 0.14);
        transform: translateY(-1px);
      }
      a.active {
        color: #fff;
        background: linear-gradient(
          120deg,
          color-mix(in srgb, var(--blue) 76%, #78b7ff),
          var(--blue)
        );
      }
      .count {
        font-family: var(--font-mono);
        font-size: 0.68rem;
        border: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
        border-radius: 999px;
        min-width: 1.2rem;
        height: 1rem;
        padding: 0 0.3rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: var(--text-muted);
      }
      .lock {
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
      }
      a.active .count {
        color: #dceeff;
        border-color: rgba(255, 255, 255, 0.35);
      }
    `,
  ];

  @property({ type: String }) active = "policy";
  @property({ type: Number }) auditCount = 0;
  @property({ type: Number }) credentialCount = 0;

  render() {
    const links = [
      { route: "policy", label: "Policy Rules", extra: null },
      {
        route: "credentials",
        label: "Credentials",
        extra: html`<span class="count"><span class="lock">L</span>${this.credentialCount}</span>`,
      },
      {
        route: "audit",
        label: "Audit Log",
        extra: html`<span class="count">${this.auditCount}</span>`,
      },
    ];

    return html`
      <nav>
        <div class="brand">agent-2fa / dashboard</div>
        <div class="tabs">
          ${links.map(
            (l) => html`
              <a
                href="#/${l.route}"
                class=${this.active === l.route ? "active" : ""}
              >
                ${l.label}
                ${l.extra ?? ""}
              </a>
            `,
          )}
        </div>
      </nav>
    `;
  }
}
