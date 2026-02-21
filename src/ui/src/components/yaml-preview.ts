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
    `,
  ];

  @property({ type: String }) yaml = "";

  render() {
    return html`
      <div class="panel">
        <div class="head">Live YAML Preview</div>
        <pre>${this.yaml}</pre>
      </div>
    `;
  }
}

