import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Action } from "../lib/types.js";
import { theme } from "../styles/theme.js";

@customElement("rule-row")
export class RuleRow extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .row {
        display: grid;
        grid-template-columns: 26px 1fr auto auto;
        gap: 0.7rem;
        align-items: center;
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--card-bg) 85%, black);
        border-radius: 12px;
        padding: 0.66rem 0.7rem;
      }
      .drag {
        font-family: var(--font-mono);
        color: var(--text-muted);
        cursor: grab;
        user-select: none;
      }
      .tool {
        font-family: var(--font-mono);
        font-size: 0.83rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .action {
        font-size: 0.74rem;
        border-radius: 999px;
        padding: 0.2rem 0.55rem;
        border: 1px solid var(--border);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--blue-soft);
      }
      .buttons {
        display: flex;
        gap: 0.4rem;
      }
      button {
        border: 1px solid var(--border);
        background: transparent;
        color: var(--text-muted);
        border-radius: 8px;
        padding: 0.22rem 0.5rem;
        cursor: pointer;
        font-size: 0.76rem;
      }
      button:hover {
        color: var(--text);
        border-color: color-mix(in srgb, var(--blue) 55%, var(--border));
      }
      button.delete:hover {
        color: #fff;
        border-color: var(--red);
        background: color-mix(in srgb, var(--red) 50%, transparent);
      }
    `,
  ];

  @property({ type: Number }) index = 0;
  @property({ type: String }) toolPattern = "";
  @property({ type: String }) action: Action = "allow";

  render() {
    return html`
      <div
        class="row"
        draggable="true"
        @dragstart=${this.onDragStart}
        @dragend=${this.onDragEnd}
        @dragover=${this.onDragOver}
        @drop=${this.onDrop}
      >
        <div class="drag">::</div>
        <div class="tool" title=${this.toolPattern}>${this.toolPattern}</div>
        <span class="action">${this.action}</span>
        <div class="buttons">
          <button @click=${this.onEdit}>Edit</button>
          <button class="delete" @click=${this.onDelete}>Delete</button>
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

