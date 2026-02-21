import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { StoredCredential } from "../lib/types.js";
import { theme } from "../styles/theme.js";

@customElement("credential-card")
export class CredentialCard extends LitElement {
  static styles = [
    theme,
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
          <div class="id" title=${cred.credentialID}>${truncate(cred.credentialID)}</div>
          <button @click=${this.onDelete}>Delete</button>
        </div>
        <div class="meta">
          <div class="row"><span>Counter</span><span>${cred.counter}</span></div>
          <div class="row"><span>Created</span><span>${formatDate(cred.createdAt)}</span></div>
          <div class="row">
            <span>Transports</span>
            <span>${cred.transports?.join(", ") || "-"}</span>
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

