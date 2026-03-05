import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import { theme } from "../styles/theme.js";

@customElement("yaml-preview")
export class YamlPreview extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .panel {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--card-bg) 92%, white),
          var(--card-bg)
        );
        overflow: hidden;
      }
      .head {
        padding: 0.55rem 0.7rem;
        border-bottom: 1px solid var(--border);
        font-size: 0.76rem;
        color: var(--text-muted);
        display: flex;
        align-items: center;
        justify-content: space-between;
        cursor: pointer;
        user-select: none;
      }
      .head:hover {
        color: var(--text);
      }
      pre {
        margin: 0;
        padding: 0.8rem;
        max-height: 72vh;
        overflow: auto;
        font-family: var(--font-mono);
        font-size: 0.77rem;
        line-height: 1.5;
        background: #0e141b;
        color: #d9e5f3;
      }
      .key {
        color: var(--text-muted);
      }
      .dash {
        color: var(--blue-soft);
      }
      .value {
        color: var(--text);
      }
      .toggle {
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 0.14rem 0.45rem;
        font-size: 0.68rem;
        color: var(--text-muted);
      }
    `,
  ];

  @property({ type: String }) yaml = "";
  @property({ type: Boolean }) collapsed = false;

  render() {
    return html`
      <div class="panel">
        <div class="head" @click=${this.onToggle}>
          <span>Live YAML Preview</span>
          <span class="toggle">${this.collapsed ? "Expand" : "Collapse"}</span>
        </div>
        ${this.collapsed ? html`` : html`<pre>${this.renderHighlightedYaml()}</pre>`}
      </div>
    `;
  }

  private onToggle() {
    this.dispatchEvent(
      new CustomEvent("toggle-yaml-preview", {
        bubbles: true,
        composed: true,
      }),
    );
  }

  private renderHighlightedYaml() {
    const lines = this.yaml.split("\n");
    return lines.map((line, index) => {
      const nextLine = index < lines.length - 1 ? "\n" : "";
      const match = line.match(/^(\s*)(-\s*)?([^:#\n][^:\n]*):(.*)$/);
      if (!match) {
        return html`${line}${nextLine}`;
      }
      const [, indent, dash, key, value] = match;
      return html`${indent}${dash ? html`<span class="dash">${dash}</span>` : ""}<span class="key">${key}:</span><span class="value">${value}</span>${nextLine}`;
    });
  }
}
