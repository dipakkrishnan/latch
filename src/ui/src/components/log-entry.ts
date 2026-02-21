import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AuditEntry } from "../lib/types.js";
import { relativeTime, sharedStyles, theme } from "../styles/theme.js";

@customElement("log-entry")
export class LogEntryRow extends LitElement {
  static styles = [
    theme,
    sharedStyles,
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
      td.striped {
        background: rgba(255, 255, 255, 0.02);
      }
      .tool {
        font-family: var(--font-mono);
        color: #c8ddf7;
        font-weight: 600;
      }
      .method,
      .action {
        font-family: var(--font-mono);
        color: var(--text-muted);
      }
      .time {
        color: var(--text);
      }
      .method-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 0.12rem 0.38rem;
        color: var(--text-muted);
        font-size: 0.7rem;
      }
      .method-icon {
        width: 0.72rem;
        text-align: center;
        opacity: 0.9;
      }
      .reason {
        color: var(--text-muted);
        max-width: 360px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        cursor: pointer;
      }
      .reason:hover,
      .reason.expanded {
        white-space: normal;
        overflow: visible;
      }
    `,
  ];

  @property({ attribute: false }) entry: AuditEntry | null = null;
  @property({ type: Boolean }) striped = false;
  @state() private reasonExpanded = false;

  render() {
    const entry = this.entry;
    if (!entry) return html``;
    const stripedClass = this.striped ? "striped" : "";
    return html`
      <td class="time ${stripedClass}" title=${formatDate(entry.timestamp)}>${relativeTime(entry.timestamp)}</td>
      <td class="method ${stripedClass}">${entry.agentClient ?? "unknown"}</td>
      <td class="method ${stripedClass}">${entry.agentId ?? "unknown"}</td>
      <td class="tool ${stripedClass}">${entry.toolName}</td>
      <td class="action ${stripedClass}">${entry.action}</td>
      <td class="${stripedClass}"><span class="badge badge-${entry.decision}">${entry.decision}</span></td>
      <td class="method ${stripedClass}">
        <span class="method-badge">
          <span class="method-icon">${methodIcon(entry.method)}</span>
          <span>${entry.method}</span>
        </span>
      </td>
      <td
        class="reason ${stripedClass} ${this.reasonExpanded ? "expanded" : ""}"
        title=${entry.reason}
        @click=${this.toggleReason}
      >
        ${entry.reason}
      </td>
    `;
  }

  private toggleReason() {
    this.reasonExpanded = !this.reasonExpanded;
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

function methodIcon(method: AuditEntry["method"]): string {
  switch (method) {
    case "policy":
      return "P";
    case "browser":
      return "B";
    case "webauthn":
      return "W";
    case "fail-open":
      return "!";
  }
}
