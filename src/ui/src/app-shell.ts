import { LitElement, html, css } from "lit";
import { customElement, state } from "lit/decorators.js";
import { theme } from "./styles/theme.js";
import "./components/nav-bar.js";
import "./pages/policy-editor.js";

@customElement("app-shell")
export class AppShell extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        min-height: 100vh;
        background: var(--bg);
        background-image:
          radial-gradient(
            circle at 10% -5%,
            rgba(88, 166, 255, 0.2),
            transparent 36%
          ),
          radial-gradient(
            circle at 90% 0%,
            rgba(35, 134, 54, 0.15),
            transparent 28%
          );
      }
      .wrap {
        max-width: 1200px;
        margin: 0 auto;
        padding: 1.2rem 1.2rem 2.2rem;
      }
      header {
        position: sticky;
        top: 0;
        z-index: 5;
        backdrop-filter: blur(8px);
        background: color-mix(in srgb, var(--bg) 82%, transparent);
        border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
        padding: 0.6rem 0;
        margin-bottom: 1rem;
      }
      main {
        overflow-y: auto;
      }
      .page-title {
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 0.6rem;
      }
      .placeholder {
        color: var(--text-muted);
        font-size: 0.95rem;
        border: 1px dashed var(--border);
        background: rgba(13, 17, 23, 0.7);
        border-radius: var(--radius);
        padding: 1rem;
      }
    `,
  ];

  @state() private route = "policy";
  private boundUpdateRoute = () => this._updateRoute();

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("hashchange", this.boundUpdateRoute);
    this._updateRoute();
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this.boundUpdateRoute);
    super.disconnectedCallback();
  }

  private _updateRoute() {
    this.route = location.hash.slice(2) || "policy";
  }

  render() {
    return html`
      <div class="wrap">
        <header><nav-bar .active=${this.route}></nav-bar></header>
        <main>${this._renderPage()}</main>
      </div>
    `;
  }

  private _renderPage() {
    switch (this.route) {
      case "policy":
        return html`<policy-editor></policy-editor>`;
      case "credentials":
        return html`
          <div class="page-title">Credentials</div>
          <div class="placeholder">
            Credential manager coming in Phase 5.
          </div>
        `;
      case "audit":
        return html`
          <div class="page-title">Audit Log</div>
          <div class="placeholder">Audit log viewer coming in Phase 6.</div>
        `;
      default:
        return html`
          <div class="page-title">Not Found</div>
          <div class="placeholder">Unknown route: ${this.route}</div>
        `;
    }
  }
}
