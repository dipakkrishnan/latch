import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { Action, PolicyRule } from "../lib/types.js";
import { theme } from "../styles/theme.js";

@customElement("rule-form")
export class RuleForm extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .overlay {
        position: fixed;
        inset: 0;
        display: grid;
        place-items: center;
        background: rgba(6, 10, 15, 0.65);
        backdrop-filter: blur(3px);
        z-index: 40;
      }
      .dialog {
        width: min(560px, calc(100vw - 2rem));
        border-radius: 16px;
        border: 1px solid var(--border);
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--card-bg) 88%, white),
          var(--card-bg)
        );
        box-shadow: 0 22px 70px rgba(0, 0, 0, 0.5);
        padding: 1.1rem 1.1rem 1rem;
        animation: dialog-pop 140ms ease-out;
      }
      @keyframes dialog-pop {
        from {
          opacity: 0;
          transform: scale(0.97);
        }
        to {
          opacity: 1;
          transform: scale(1);
        }
      }
      h3 {
        font-size: 1rem;
        margin-bottom: 0.9rem;
      }
      .field {
        display: grid;
        gap: 0.38rem;
        margin-bottom: 0.8rem;
      }
      label {
        color: var(--text-muted);
        font-size: 0.82rem;
      }
      input,
      select {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.56rem 0.65rem;
        background: #0f141a;
        color: var(--text);
        font-family: var(--font-mono);
        font-size: 0.83rem;
      }
      input:focus,
      select:focus {
        outline: none;
        border-color: color-mix(in srgb, var(--blue) 82%, var(--border));
        box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.52);
      }
      .regex-check {
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.65rem;
        background: rgba(13, 17, 23, 0.74);
      }
      .regex-label {
        color: var(--text-muted);
        font-size: 0.74rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.45rem;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid color-mix(in srgb, var(--border) 75%, transparent);
      }
      .match {
        font-size: 0.8rem;
        margin-top: 0.35rem;
      }
      .ok {
        color: var(--green-bright);
      }
      .bad {
        color: var(--red-bright);
      }
      .error {
        color: var(--red-bright);
        font-size: 0.8rem;
      }
      .buttons {
        display: flex;
        justify-content: flex-end;
        gap: 0.55rem;
        margin-top: 0.9rem;
      }
      button {
        border-radius: 10px;
        border: 1px solid var(--border);
        padding: 0.44rem 0.72rem;
        cursor: pointer;
        font-weight: 600;
        font-size: 0.82rem;
      }
      .cancel {
        background: transparent;
        color: var(--text-muted);
      }
      .save {
        background: var(--blue);
        border-color: color-mix(in srgb, var(--blue) 75%, #fff);
        color: #061529;
      }
    `,
  ];

  @property({ type: Boolean }) open = false;
  @property({ attribute: false }) initialRule: PolicyRule | null = null;
  @property({ type: String }) title = "Add Rule";

  @state() private toolPattern = "";
  @state() private action: Action = "ask";
  @state() private regexInput = "";
  @state() private formError = "";

  protected willUpdate(changed: Map<string, unknown>): void {
    if (changed.has("open") && this.open) {
      this.toolPattern = this.initialRule?.match.tool ?? "";
      this.action = this.initialRule?.action ?? "ask";
      this.regexInput = "";
      this.formError = "";
    }
  }

  render() {
    if (!this.open) return html``;
    const regexTest = this.testRegex(this.toolPattern, this.regexInput);

    return html`
      <div class="overlay" @click=${this.onOverlayClick}>
        <div class="dialog" @click=${this.onDialogClick}>
          <h3>${this.title}</h3>
          <form @submit=${this.onSubmit}>
            <div class="field">
              <label>Tool Pattern (regex)</label>
              <input
                .value=${this.toolPattern}
                @input=${this.onPatternInput}
                placeholder="Bash|Edit|Write"
              />
            </div>
            <div class="field">
              <label>Action</label>
              <select .value=${this.action} @change=${this.onActionChange}>
                <option value="allow">allow</option>
                <option value="ask">ask</option>
                <option value="deny">deny</option>
                <option value="browser">browser</option>
                <option value="webauthn">webauthn</option>
              </select>
            </div>
            <div class="field">
              <label>Regex Tester (tool name)</label>
              <div class="regex-check">
                <div class="regex-label">Match Preview</div>
                <input
                  .value=${this.regexInput}
                  @input=${this.onRegexInput}
                  placeholder="Try: Bash or Read"
                />
                <div class="match ${regexTest.ok ? "ok" : "bad"}">
                  ${regexTest.message}
                </div>
              </div>
            </div>
            ${this.formError ? html`<div class="error">${this.formError}</div>` : ""}
            <div class="buttons">
              <button type="button" class="cancel" @click=${this.onCancel}>Cancel</button>
              <button type="submit" class="save">Save Rule</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  private onSubmit(event: Event) {
    event.preventDefault();
    this.onSave();
  }

  private onPatternInput(event: Event) {
    this.toolPattern = (event.target as HTMLInputElement).value;
    this.formError = "";
  }

  private onActionChange(event: Event) {
    this.action = (event.target as HTMLSelectElement).value as Action;
  }

  private onRegexInput(event: Event) {
    this.regexInput = (event.target as HTMLInputElement).value;
  }

  private onCancel() {
    this.dispatchEvent(new CustomEvent("cancel-rule-form"));
  }

  private onOverlayClick() {
    this.onCancel();
  }

  private onDialogClick(event: Event) {
    event.stopPropagation();
  }

  private onSave() {
    const pattern = this.toolPattern.trim();
    if (!pattern) {
      this.formError = "Tool pattern is required.";
      return;
    }

    const test = this.testRegex(pattern, this.regexInput);
    if (!test.validRegex) {
      this.formError = "Invalid regex pattern.";
      return;
    }

    this.dispatchEvent(
      new CustomEvent("save-rule-form", {
        detail: {
          rule: {
            match: { tool: pattern },
            action: this.action,
          } as PolicyRule,
        },
      }),
    );
  }

  private testRegex(pattern: string, input: string): {
    validRegex: boolean;
    ok: boolean;
    message: string;
  } {
    const trimmed = pattern.trim();
    if (!trimmed) {
      return {
        validRegex: true,
        ok: false,
        message: "Enter a pattern to test.",
      };
    }

    try {
      const regex = new RegExp(`^(?:${trimmed})$`);
      if (!input) {
        return {
          validRegex: true,
          ok: false,
          message: "Type a tool name to preview match behavior.",
        };
      }
      const matched = regex.test(input);
      return {
        validRegex: true,
        ok: matched,
        message: matched ? "Matches this tool name." : "Does not match this tool name.",
      };
    } catch {
      return {
        validRegex: false,
        ok: false,
        message: "Pattern is not valid regex.",
      };
    }
  }
}
