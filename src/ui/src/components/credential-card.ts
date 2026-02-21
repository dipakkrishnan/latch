import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { StoredCredential } from "../lib/types.js";
import { relativeTime, sharedStyles, theme } from "../styles/theme.js";

@customElement("credential-card")
export class CredentialCard extends LitElement {
  static styles = [
    theme,
    sharedStyles,
    css`
      :host {
        display: block;
      }
      .card {
        border: 1px solid var(--border);
        border-radius: 13px;
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--card-bg) 90%, white),
          var(--card-bg)
        );
        padding: 0.74rem;
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 0.6rem;
      }
      .head-left {
        display: grid;
        gap: 0.38rem;
        min-width: 0;
      }
      .topline {
        display: inline-flex;
        align-items: center;
        gap: 0.42rem;
      }
      .key-icon {
        width: 1.05rem;
        height: 1.05rem;
        border: 1px solid var(--border);
        border-radius: 999px;
        position: relative;
      }
      .key-icon::before {
        content: "";
        position: absolute;
        width: 0.26rem;
        height: 0.26rem;
        border: 1px solid var(--blue-soft);
        border-radius: 999px;
        top: 0.21rem;
        left: 0.21rem;
      }
      .key-icon::after {
        content: "";
        position: absolute;
        width: 0.35rem;
        height: 1px;
        background: var(--blue-soft);
        top: 0.54rem;
        left: 0.49rem;
        box-shadow: 0.15rem 0 0 var(--blue-soft);
      }
      .id {
        font-family: var(--font-mono);
        font-size: 0.79rem;
        color: var(--blue-soft);
        word-break: break-all;
      }
      .meta {
        margin-top: 0.55rem;
        display: grid;
        gap: 0.3rem;
      }
      .row {
        display: flex;
        justify-content: space-between;
        gap: 0.6rem;
        color: var(--text-muted);
        font-size: 0.78rem;
      }
      .row span:last-child {
        color: var(--text);
        font-family: var(--font-mono);
      }
      .date {
        text-align: right;
      }
      .date .rel {
        color: var(--text);
      }
      .date .abs {
        font-size: 0.7rem;
        color: var(--text-muted);
      }
      .transports {
        display: inline-flex;
        gap: 0.26rem;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      .transport {
        border-radius: 999px;
        border: 1px solid var(--border);
        padding: 0.1rem 0.35rem;
        font-size: 0.68rem;
        color: var(--text-muted);
      }
      button {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.3rem 0.52rem;
        font-size: 0.74rem;
        cursor: pointer;
        background: transparent;
        color: var(--text-muted);
      }
      button:hover {
        background: color-mix(in srgb, var(--red) 40%, transparent);
        border-color: var(--red);
        color: #fff;
      }
    `,
  ];

  @property({ attribute: false }) credential: StoredCredential | null = null;

  render() {
    const cred = this.credential;
    if (!cred) return html``;

    return html`
      <div class="card">
        <div class="head">
          <div class="head-left">
            <div class="topline">
              <span class="key-icon" aria-hidden="true"></span>
              <span class="status-dot" title="Active credential"></span>
            </div>
            <div class="id" title=${cred.credentialID}>${truncate(cred.credentialID)}</div>
          </div>
          <button @click=${this.onDelete}>Delete</button>
        </div>
        <div class="meta">
          <div class="row"><span>Counter</span><span>${cred.counter}</span></div>
          <div class="row">
            <span>Created</span>
            <span class="date" title=${formatDate(cred.createdAt)}>
              <div class="rel">enrolled ${relativeTime(cred.createdAt)}</div>
              <div class="abs">${formatDate(cred.createdAt)}</div>
            </span>
          </div>
          <div class="row">
            <span>Transports</span>
            <span class="transports">
              ${(cred.transports ?? []).length === 0
                ? html`<span class="transport">-</span>`
                : (cred.transports ?? []).map(
                    (transport) => html`<span class="transport">${transport}</span>`,
                  )}
            </span>
          </div>
        </div>
      </div>
    `;
  }

  private onDelete() {
    if (!this.credential) return;
    this.dispatchEvent(
      new CustomEvent("delete-credential", {
        detail: { credentialID: this.credential.credentialID },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

function truncate(id: string): string {
  if (id.length <= 24) return id;
  return `${id.slice(0, 10)}...${id.slice(-10)}`;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
