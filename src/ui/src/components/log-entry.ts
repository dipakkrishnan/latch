import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { AuditEntry } from "../lib/types.js";
import { theme } from "../styles/theme.js";

@customElement("log-entry")
export class LogEntryRow extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: contents;
      }
      td {
        padding: 0.6rem 0.55rem;
        border-top: 1px solid color-mix(in srgb, var(--border) 80%, transparent);
        font-size: 0.8rem;
        vertical-align: top;
      }
      .tool {
        font-family: var(--font-mono);
        color: var(--blue-soft);
      }
      .method,
      .action {
        font-family: var(--font-mono);
        color: var(--text-muted);
      }
      .decision {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 58px;
        padding: 0.16rem 0.45rem;
        border-radius: 999px;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        border: 1px solid var(--border);
      }
      .allow {
        color: var(--green-bright);
        border-color: color-mix(in srgb, var(--green) 70%, var(--border));
      }
      .deny {
        color: var(--red-bright);
        border-color: color-mix(in srgb, var(--red) 70%, var(--border));
      }
      .ask {
        color: var(--amber);
      }
      .reason {
        color: var(--text-muted);
        max-width: 360px;
      }
    `,
  ];

  @property({ attribute: false }) entry: AuditEntry | null = null;

  render() {
    const entry = this.entry;
    if (!entry) return html``;
    return html`
      <td>${formatDate(entry.timestamp)}</td>
      <td class="tool">${entry.toolName}</td>
      <td class="action">${entry.action}</td>
      <td><span class="decision ${entry.decision}">${entry.decision}</span></td>
      <td class="method">${entry.method}</td>
      <td class="reason">${entry.reason}</td>
    `;
  }
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
    second: "2-digit",
  }).format(date);
}

