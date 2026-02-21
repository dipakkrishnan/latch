import { LitElement, html, css } from "lit";
import { customElement, state } from "lit/decorators.js";
import { theme } from "./styles/theme.js";
import "./components/nav-bar.js";

@customElement("app-shell")
export class AppShell extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: flex;
        min-height: 100vh;
        background: var(--bg);
      }
      main {
        flex: 1;
        padding: 2rem;
        overflow-y: auto;
      }
      .page-title {
        font-size: 1.4rem;
        font-weight: 600;
        margin-bottom: 1rem;
      }
      .placeholder {
        color: var(--text-muted);
        font-size: 0.95rem;
      }
    `,
  ];

  @state() private route = "policy";

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("hashchange", () => this._updateRoute());
    this._updateRoute();
  }

  private _updateRoute() {
    this.route = location.hash.slice(2) || "policy";
  }

  render() {
    return html`
      <nav-bar .active=${this.route}></nav-bar>
      <main>${this._renderPage()}</main>
    `;
  }

  private _renderPage() {
    switch (this.route) {
      case "policy":
        return html`
          <div class="page-title">Policy Rules</div>
          <div class="placeholder">Policy editor coming in Phase 4.</div>
        `;
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
