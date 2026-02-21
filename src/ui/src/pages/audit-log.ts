import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { getAuditLog, getAuditStats } from "../lib/api-client.js";
import type { AuditEntry, AuditStats } from "../lib/types.js";
import { theme } from "../styles/theme.js";
import "../components/log-entry.js";

const PAGE_SIZE = 20;

@customElement("audit-log-page")
export class AuditLogPage extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .header {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.8rem;
        flex-wrap: wrap;
      }
      h1 {
        margin: 0;
        font-size: 1.35rem;
      }
      .sub {
        margin-top: 0.32rem;
        color: var(--text-muted);
        font-size: 0.88rem;
      }
      .refresh {
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.44rem 0.72rem;
        cursor: pointer;
        background: transparent;
        color: var(--text);
        font-weight: 600;
        font-size: 0.82rem;
      }
      .stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.6rem;
        margin-bottom: 0.75rem;
      }
      .stat {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--card-bg) 90%, white),
          var(--card-bg)
        );
        padding: 0.62rem 0.7rem;
      }
      .k {
        color: var(--text-muted);
        font-size: 0.72rem;
      }
      .v {
        margin-top: 0.2rem;
        font-family: var(--font-mono);
        font-size: 1rem;
      }
      .filters {
        display: grid;
        grid-template-columns: 1fr 170px;
        gap: 0.5rem;
        margin-bottom: 0.65rem;
      }
      input,
      select {
        border: 1px solid var(--border);
        border-radius: 10px;
        background: #0f141b;
        color: var(--text);
        padding: 0.5rem 0.58rem;
        font-size: 0.82rem;
      }
      .table-wrap {
        border: 1px solid var(--border);
        border-radius: var(--radius);
        overflow: auto;
        background: color-mix(in srgb, var(--card-bg) 95%, black);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        min-width: 940px;
      }
      thead th {
        text-align: left;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        color: var(--text-muted);
        padding: 0.5rem 0.55rem;
        border-bottom: 1px solid var(--border);
      }
      .pagination {
        margin-top: 0.62rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.8rem;
      }
      .meta {
        color: var(--text-muted);
        font-size: 0.78rem;
      }
      .pbtns {
        display: inline-flex;
        gap: 0.42rem;
      }
      .pbtns button {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.3rem 0.55rem;
        background: transparent;
        color: var(--text);
        cursor: pointer;
      }
      button:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }
      .status {
        margin-bottom: 0.6rem;
        font-size: 0.82rem;
      }
      .error {
        color: var(--red-bright);
      }
      .empty {
        border: 1px dashed var(--border);
        border-radius: 10px;
        color: var(--text-muted);
        text-align: center;
        padding: 0.9rem;
      }
      @media (max-width: 900px) {
        .stats {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .filters {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];

  @state() private entries: AuditEntry[] = [];
  @state() private stats: AuditStats = {
    total: 0,
    approvals: 0,
    denials: 0,
    asks: 0,
    byTool: {},
  };
  @state() private loading = false;
  @state() private error = "";
  @state() private toolFilter = "";
  @state() private decisionFilter = "all";
  @state() private page = 0;

  async connectedCallback(): Promise<void> {
    super.connectedCallback();
    await this.refresh();
  }

  render() {
    const filtered = this.filteredEntries();
    const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const safePage = Math.min(this.page, pageCount - 1);
    const start = safePage * PAGE_SIZE;
    const visible = filtered.slice(start, start + PAGE_SIZE);

    return html`
      <div class="header">
        <div>
          <h1>Audit Log</h1>
          <div class="sub">Review approval decisions by tool, action, and method.</div>
        </div>
        <button class="refresh" ?disabled=${this.loading} @click=${this.refresh}>
          ${this.loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div class="stats">
        <div class="stat"><div class="k">Total</div><div class="v">${this.stats.total}</div></div>
        <div class="stat"><div class="k">Approvals</div><div class="v">${this.stats.approvals}</div></div>
        <div class="stat"><div class="k">Denials</div><div class="v">${this.stats.denials}</div></div>
        <div class="stat"><div class="k">Asks</div><div class="v">${this.stats.asks}</div></div>
      </div>

      <div class="filters">
        <input
          .value=${this.toolFilter}
          @input=${this.onToolFilter}
          placeholder="Filter by tool name"
        />
        <select .value=${this.decisionFilter} @change=${this.onDecisionFilter}>
          <option value="all">All decisions</option>
          <option value="allow">allow</option>
          <option value="ask">ask</option>
          <option value="deny">deny</option>
        </select>
      </div>

      ${this.error ? html`<div class="status error">${this.error}</div>` : ""}

      ${visible.length === 0
        ? html`<div class="empty">No log entries match these filters.</div>`
        : html`
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Tool</th>
                    <th>Action</th>
                    <th>Decision</th>
                    <th>Method</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  ${visible.map(
                    (entry) =>
                      html`<tr><log-entry .entry=${entry}></log-entry></tr>`,
                  )}
                </tbody>
              </table>
            </div>
            <div class="pagination">
              <div class="meta">
                Showing ${visible.length} of ${filtered.length} filtered entries
              </div>
              <div class="pbtns">
                <button ?disabled=${safePage <= 0} @click=${this.prevPage}>Prev</button>
                <button ?disabled=${safePage >= pageCount - 1} @click=${this.nextPage}>
                  Next
                </button>
              </div>
            </div>
          `}
    `;
  }

  private refresh = async () => {
    this.loading = true;
    this.error = "";
    try {
      const [entries, stats] = await Promise.all([
        getAuditLog(500, 0),
        getAuditStats(),
      ]);
      this.entries = entries;
      this.stats = stats;
      this.page = 0;
    } catch (err) {
      this.error = `Failed to load audit data: ${String(err)}`;
    } finally {
      this.loading = false;
    }
  };

  private onToolFilter(event: Event) {
    this.toolFilter = (event.target as HTMLInputElement).value;
    this.page = 0;
  }

  private onDecisionFilter(event: Event) {
    this.decisionFilter = (event.target as HTMLSelectElement).value;
    this.page = 0;
  }

  private filteredEntries(): AuditEntry[] {
    const tool = this.toolFilter.trim().toLowerCase();
    const decision = this.decisionFilter;
    return this.entries.filter((entry) => {
      if (tool && !entry.toolName.toLowerCase().includes(tool)) return false;
      if (decision !== "all" && entry.decision !== decision) return false;
      return true;
    });
  }

  private prevPage = () => {
    this.page = Math.max(0, this.page - 1);
  };

  private nextPage = () => {
    const maxPage = Math.max(0, Math.ceil(this.filteredEntries().length / PAGE_SIZE) - 1);
    this.page = Math.min(maxPage, this.page + 1);
  };
}

