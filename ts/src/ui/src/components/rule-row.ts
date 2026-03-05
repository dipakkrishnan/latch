import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Action } from "../lib/types.js";
import { sharedStyles, theme } from "../styles/theme.js";

@customElement("rule-row")
export class RuleRow extends LitElement {
  static styles = [
    theme,
    sharedStyles,
    css`
      :host {
        display: block;
      }
      .row {
        display: grid;
        grid-template-columns: auto 24px 1fr auto auto;
        gap: 0.7rem;
        align-items: center;
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--card-bg) 85%, black);
        border-radius: 12px;
        padding: 0.66rem 0.7rem;
        position: relative;
        transition: transform var(--transition), border-color var(--transition), background var(--transition);
      }
      .row::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 2px;
        border-top-left-radius: 12px;
        border-bottom-left-radius: 12px;
        background: var(--border);
      }
      .row:hover {
        transform: translateY(-1px);
        border-color: color-mix(in srgb, var(--blue) 35%, var(--border));
        background: color-mix(in srgb, var(--card-bg) 90%, #1f2d3a);
      }
      .row.action-allow::before {
        background: var(--green-bright);
      }
      .row.action-ask::before {
        background: var(--amber);
      }
      .row.action-deny::before {
        background: var(--red-bright);
      }
      .row.action-browser::before {
        background: var(--blue-soft);
      }
      .row.action-webauthn::before {
        background: var(--purple);
      }
      .order {
        font-family: var(--font-mono);
        font-size: 0.7rem;
        color: var(--text-muted);
        border: 1px solid var(--border);
        border-radius: 999px;
        min-width: 1.7rem;
        height: 1.2rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .drag {
        width: 16px;
        height: 16px;
        cursor: grab;
        user-select: none;
        position: relative;
        opacity: 0.8;
      }
      .drag::before {
        content: "";
        position: absolute;
        inset: 0;
        background:
          radial-gradient(circle, var(--text-muted) 1.1px, transparent 1.2px) 0 0 / 8px 8px,
          radial-gradient(circle, var(--text-muted) 1.1px, transparent 1.2px) 4px 4px / 8px 8px;
      }
      .tool {
        font-family: var(--font-mono);
        font-size: 0.9rem;
        font-weight: 600;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .buttons {
        display: flex;
        gap: 0.3rem;
      }
      button {
        border: 1px solid var(--border);
        background: transparent;
        color: var(--text-muted);
        border-radius: 999px;
        width: 1.5rem;
        height: 1.5rem;
        padding: 0;
        cursor: pointer;
        font-size: 0.76rem;
        opacity: 0.78;
        transition: all var(--transition);
      }
      button:hover {
        color: var(--text);
        border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
        opacity: 1;
      }
      button.delete:hover {
        color: #fff;
        border-color: var(--red);
        background: color-mix(in srgb, var(--red) 50%, transparent);
      }
    `,
  ];

  @property({ type: Number }) index = 0;
  @property({ type: Number }) order = 0;
  @property({ type: String }) toolPattern = "";
  @property({ type: String }) action: Action = "allow";

  render() {
    return html`
      <div
        class="row action-${this.action}"
        draggable="true"
        @dragstart=${this.onDragStart}
        @dragend=${this.onDragEnd}
        @dragover=${this.onDragOver}
        @drop=${this.onDrop}
      >
        <div class="order">#${this.order}</div>
        <div class="drag" aria-hidden="true"></div>
        <div class="tool" title=${this.toolPattern}>${this.toolPattern}</div>
        <span class="badge badge-${this.action}">${this.action}</span>
        <div class="buttons">
          <button @click=${this.onEdit} title="Edit rule" aria-label="Edit rule">✎</button>
          <button class="delete" @click=${this.onDelete} title="Delete rule" aria-label="Delete rule">×</button>
        </div>
      </div>
    `;
  }

  private onEdit() {
    this.dispatchEvent(
      new CustomEvent("edit-rule", {
        detail: { index: this.index },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onDelete() {
    this.dispatchEvent(
      new CustomEvent("delete-rule", {
        detail: { index: this.index },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onDragStart() {
    this.dispatchEvent(
      new CustomEvent("drag-rule-start", {
        detail: { index: this.index },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onDragEnd() {
    this.dispatchEvent(
      new CustomEvent("drag-rule-end", {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onDragOver(event: DragEvent) {
    event.preventDefault();
  }

  private onDrop(event: DragEvent) {
    event.preventDefault();
    this.dispatchEvent(
      new CustomEvent("drop-on-rule", {
        detail: { index: this.index },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
