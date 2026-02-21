import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { stringify as stringifyYaml } from "yaml";
import { getPolicy, savePolicy, validatePolicy } from "../lib/api-client.js";
import type { Action, PolicyConfig, PolicyRule } from "../lib/types.js";
import { theme } from "../styles/theme.js";
import "../components/rule-row.js";
import "../components/rule-form.js";
import "../components/yaml-preview.js";

interface UiRule {
  id: string;
  match: { tool: string };
  action: Action;
}

@customElement("policy-editor")
export class PolicyEditor extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .header {
        margin-bottom: 0.9rem;
      }
      h1 {
        margin: 0;
        font-size: 1.35rem;
        letter-spacing: 0.01em;
      }
      .subtitle {
        margin-top: 0.35rem;
        color: var(--text-muted);
        font-size: 0.88rem;
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
        gap: 0.95rem;
      }
      .card {
        border: 1px solid var(--border);
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--card-bg) 90%, white),
          var(--card-bg)
        );
        border-radius: var(--radius);
        padding: 0.8rem;
      }
      .toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.7rem;
        flex-wrap: wrap;
      }
      .control {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        color: var(--text-muted);
        font-size: 0.82rem;
      }
      select {
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.4rem 0.56rem;
        background: #10151c;
        color: var(--text);
      }
      button {
        border-radius: 10px;
        border: 1px solid var(--border);
        padding: 0.43rem 0.74rem;
        font-weight: 600;
        font-size: 0.82rem;
        cursor: pointer;
      }
      .ghost {
        background: transparent;
        color: var(--text);
      }
      .primary {
        background: var(--blue);
        border-color: color-mix(in srgb, var(--blue) 70%, #fff);
        color: #071527;
      }
      .save {
        background: linear-gradient(
          120deg,
          color-mix(in srgb, var(--green) 82%, #63d67f),
          var(--green)
        );
        border-color: color-mix(in srgb, var(--green) 70%, #fff);
        color: #031109;
      }
      button:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }
      .rules {
        display: grid;
        gap: 0.5rem;
      }
      .hint {
        color: var(--text-muted);
        font-size: 0.78rem;
        margin-bottom: 0.55rem;
      }
      .status {
        margin-top: 0.62rem;
        font-size: 0.8rem;
      }
      .ok {
        color: var(--green-bright);
      }
      .error {
        color: var(--red-bright);
      }
      .errors {
        margin-top: 0.5rem;
        border: 1px solid color-mix(in srgb, var(--red) 55%, var(--border));
        background: rgba(218, 54, 51, 0.08);
        border-radius: 10px;
        padding: 0.55rem 0.65rem;
      }
      .errors div {
        font-family: var(--font-mono);
        font-size: 0.74rem;
        color: #ffd4d2;
      }
      .empty {
        color: var(--text-muted);
        border: 1px dashed var(--border);
        border-radius: 11px;
        padding: 0.8rem;
        text-align: center;
      }
      @media (max-width: 930px) {
        .layout {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  @state() private loaded = false;
  @state() private loading = false;
  @state() private saving = false;
  @state() private error = "";
  @state() private message = "";
  @state() private defaultAction: Action = "allow";
  @state() private rules: UiRule[] = [];
  @state() private dialogOpen = false;
  @state() private editingIndex: number | null = null;
  @state() private validationErrors: string[] = [];
  @state() private draggedIndex: number | null = null;

  async connectedCallback(): Promise<void> {
    super.connectedCallback();
    await this.load();
  }

  render() {
    if (!this.loaded && this.loading) {
      return html`<div class="status">Loading policy...</div>`;
    }

    const yaml = stringifyYaml(this.toPolicyConfig());
    const editingRule =
      this.editingIndex === null ? null : this.rules[this.editingIndex] ?? null;

    return html`
      <div class="header">
        <h1>Policy Rules</h1>
        <div class="subtitle">
          Define match rules in order. First matching rule wins.
        </div>
      </div>
      <div class="layout">
        <div class="card">
          <div class="toolbar">
            <div class="control">
              <span>Default Action</span>
              <select .value=${this.defaultAction} @change=${this.onDefaultActionChange}>
                <option value="allow">allow</option>
                <option value="ask">ask</option>
                <option value="deny">deny</option>
                <option value="browser">browser</option>
                <option value="webauthn">webauthn</option>
              </select>
            </div>
            <div class="control">
              <button class="primary" @click=${this.onAddRule}>Add Rule</button>
              <button class="save" ?disabled=${this.saving} @click=${this.onSavePolicy}>
                ${this.saving ? "Saving..." : "Save Policy"}
              </button>
            </div>
          </div>
          <div class="hint">Drag rows by handle to reorder rules.</div>
          <div
            class="rules"
            @edit-rule=${this.onEditRule}
            @delete-rule=${this.onDeleteRule}
            @drag-rule-start=${this.onDragStart}
            @drag-rule-end=${this.onDragEnd}
            @drop-on-rule=${this.onDropOnRule}
          >
            ${this.rules.length === 0
              ? html`<div class="empty">No rules yet. Add your first rule.</div>`
              : this.rules.map(
                  (rule, index) => html`
                    <rule-row
                      .index=${index}
                      .toolPattern=${rule.match.tool}
                      .action=${rule.action}
                    ></rule-row>
                  `,
                )}
          </div>
          ${this.message ? html`<div class="status ok">${this.message}</div>` : ""}
          ${this.error ? html`<div class="status error">${this.error}</div>` : ""}
          ${this.validationErrors.length > 0
            ? html`
                <div class="errors">
                  ${this.validationErrors.map((item) => html`<div>${item}</div>`)}
                </div>
              `
            : ""}
        </div>
        <yaml-preview .yaml=${yaml}></yaml-preview>
      </div>
      <rule-form
        .open=${this.dialogOpen}
        .initialRule=${editingRule}
        .title=${this.editingIndex === null ? "Add Rule" : "Edit Rule"}
        @cancel-rule-form=${this.closeDialog}
        @save-rule-form=${this.onSaveRuleForm}
      ></rule-form>
    `;
  }

  private async load() {
    this.loading = true;
    this.error = "";
    this.message = "";
    this.validationErrors = [];
    try {
      const config = await getPolicy();
      this.defaultAction = config.defaultAction;
      this.rules = config.rules.map((rule) => ({
        ...rule,
        id: this.makeId(),
      }));
      this.loaded = true;
    } catch (err) {
      this.error = `Failed to load policy: ${String(err)}`;
    } finally {
      this.loading = false;
    }
  }

  private onDefaultActionChange(event: Event) {
    this.defaultAction = (event.target as HTMLSelectElement).value as Action;
    this.message = "";
    this.error = "";
  }

  private onAddRule() {
    this.editingIndex = null;
    this.dialogOpen = true;
  }

  private onEditRule(event: Event) {
    const detail = (event as CustomEvent<{ index: number }>).detail;
    if (!detail) return;
    this.editingIndex = detail.index;
    this.dialogOpen = true;
  }

  private onDeleteRule(event: Event) {
    const detail = (event as CustomEvent<{ index: number }>).detail;
    if (!detail) return;
    this.rules = this.rules.filter((_, idx) => idx !== detail.index);
    this.message = "";
    this.error = "";
  }

  private onSaveRuleForm(event: Event) {
    const detail = (event as CustomEvent<{ rule: PolicyRule }>).detail;
    if (!detail) return;
    const incoming = detail.rule;
    if (this.editingIndex === null) {
      this.rules = [
        ...this.rules,
        {
          ...incoming,
          id: this.makeId(),
        },
      ];
    } else {
      this.rules = this.rules.map((rule, idx) =>
        idx === this.editingIndex
          ? {
              ...incoming,
              id: rule.id,
            }
          : rule,
      );
    }
    this.closeDialog();
    this.message = "";
    this.error = "";
  }

  private closeDialog() {
    this.dialogOpen = false;
    this.editingIndex = null;
  }

  private onDragStart(event: Event) {
    const detail = (event as CustomEvent<{ index: number }>).detail;
    if (!detail) return;
    this.draggedIndex = detail.index;
  }

  private onDragEnd() {
    this.draggedIndex = null;
  }

  private onDropOnRule(event: Event) {
    const detail = (event as CustomEvent<{ index: number }>).detail;
    if (!detail) return;
    if (this.draggedIndex === null) return;
    const from = this.draggedIndex;
    const to = detail.index;
    if (from === to) return;

    const next = [...this.rules];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(to, 0, moved);
    this.rules = next;
    this.draggedIndex = null;
  }

  private async onSavePolicy() {
    this.saving = true;
    this.message = "";
    this.error = "";
    this.validationErrors = [];

    const config = this.toPolicyConfig();

    try {
      const validation = await validatePolicy(config);
      if (!validation.valid) {
        this.validationErrors = (validation.errors ?? []).map((item: any) => {
          const path = Array.isArray(item.path) ? item.path.join(".") : "";
          return `${path ? `${path}: ` : ""}${item.message ?? "Invalid value"}`;
        });
        this.error = "Policy validation failed.";
        return;
      }

      await savePolicy(config);
      this.message = "Policy saved.";
      await this.load();
    } catch (err) {
      this.error = `Failed to save policy: ${String(err)}`;
    } finally {
      this.saving = false;
    }
  }

  private toPolicyConfig(): PolicyConfig {
    return {
      defaultAction: this.defaultAction,
      rules: this.rules.map(({ id: _id, ...rule }) => rule),
    };
  }

  private makeId(): string {
    return `rule-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }
}
