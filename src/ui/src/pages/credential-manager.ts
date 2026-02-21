import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import {
  deleteCredential,
  getCredentials,
  getEnrollOptions,
  verifyEnrollment,
} from "../lib/api-client.js";
import type { StoredCredential } from "../lib/types.js";
import { theme } from "../styles/theme.js";
import "../components/credential-card.js";

interface EnrollmentOptions {
  challengeId: string;
  challenge: string;
  user: { id: string };
  excludeCredentials?: Array<{ id: string; type: "public-key" }>;
  [key: string]: unknown;
}

@customElement("credential-manager")
export class CredentialManager extends LitElement {
  static styles = [
    theme,
    css`
      :host {
        display: block;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1rem;
        margin-bottom: 0.9rem;
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
      .actions {
        display: inline-flex;
        gap: 0.55rem;
      }
      button {
        border-radius: 10px;
        border: 1px solid var(--border);
        padding: 0.46rem 0.75rem;
        font-weight: 600;
        font-size: 0.82rem;
        cursor: pointer;
      }
      .enroll {
        color: #06170d;
        background: linear-gradient(
          120deg,
          color-mix(in srgb, var(--green) 80%, #5fdb7f),
          var(--green)
        );
        border-color: color-mix(in srgb, var(--green) 65%, #fff);
      }
      .ghost {
        background: transparent;
        color: var(--text);
      }
      button:disabled {
        opacity: 0.48;
        cursor: not-allowed;
      }
      .cards {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 0.65rem;
      }
      .empty {
        border: 1px dashed var(--border);
        border-radius: var(--radius);
        text-align: center;
        color: var(--text-muted);
        padding: 1rem;
      }
      .status {
        margin-bottom: 0.65rem;
        font-size: 0.82rem;
      }
      .ok {
        color: var(--green-bright);
      }
      .error {
        color: var(--red-bright);
      }
      .meta {
        color: var(--text-muted);
        font-size: 0.8rem;
      }
    `,
  ];

  @state() private credentials: StoredCredential[] = [];
  @state() private loading = false;
  @state() private busy = false;
  @state() private error = "";
  @state() private message = "";

  async connectedCallback(): Promise<void> {
    super.connectedCallback();
    await this.loadCredentials();
  }

  render() {
    return html`
      <div class="header">
        <div>
          <h1>Credentials</h1>
          <div class="sub">Manage enrolled passkeys for tool-call approvals.</div>
        </div>
        <div class="actions">
          <button class="ghost" ?disabled=${this.loading || this.busy} @click=${this.loadCredentials}>
            Refresh
          </button>
          <button class="enroll" ?disabled=${this.busy} @click=${this.enrollPasskey}>
            ${this.busy ? "Working..." : "Enroll Passkey"}
          </button>
        </div>
      </div>
      <div class="meta">${this.credentials.length} credential(s)</div>
      ${this.message ? html`<div class="status ok">${this.message}</div>` : ""}
      ${this.error ? html`<div class="status error">${this.error}</div>` : ""}
      ${this.credentials.length === 0
        ? html`
            <div class="empty">
              No passkeys enrolled yet. Click <strong>Enroll Passkey</strong> to add one.
            </div>
          `
        : html`
            <div class="cards" @delete-credential=${this.onDeleteCredential}>
              ${this.credentials.map(
                (credential) => html`
                  <credential-card .credential=${credential}></credential-card>
                `,
              )}
            </div>
          `}
    `;
  }

  private loadCredentials = async () => {
    this.loading = true;
    this.error = "";
    this.message = "";
    try {
      this.credentials = await getCredentials();
    } catch (err) {
      this.error = `Failed to load credentials: ${String(err)}`;
    } finally {
      this.loading = false;
    }
  };

  private async onDeleteCredential(event: Event) {
    const detail = (event as CustomEvent<{ credentialID: string }>).detail;
    if (!detail?.credentialID) return;

    const confirmed = window.confirm("Delete this credential?");
    if (!confirmed) return;

    this.busy = true;
    this.error = "";
    this.message = "";
    try {
      await deleteCredential(detail.credentialID);
      this.message = "Credential deleted.";
      await this.loadCredentials();
    } catch (err) {
      this.error = `Failed to delete credential: ${String(err)}`;
    } finally {
      this.busy = false;
    }
  }

  private enrollPasskey = async () => {
    this.busy = true;
    this.error = "";
    this.message = "";

    try {
      if (window.location.hostname !== "localhost") {
        throw new Error(
          "Open the dashboard on http://localhost (not 127.0.0.1) for passkey enrollment.",
        );
      }
      if (!("credentials" in navigator) || !window.PublicKeyCredential) {
        throw new Error("WebAuthn is not supported in this browser.");
      }

      const options = (await getEnrollOptions()) as EnrollmentOptions;
      if (!options.challengeId || typeof options.challengeId !== "string") {
        throw new Error("Missing enrollment challenge id.");
      }

      const publicKey = this.preparePublicKeyOptions(options);
      const credential = (await navigator.credentials.create({
        publicKey,
      })) as PublicKeyCredential | null;

      if (!credential) {
        throw new Error("Passkey enrollment was cancelled.");
      }

      const response = credential.response as AuthenticatorAttestationResponse;
      const registrationResponse = {
        id: credential.id,
        rawId: toBase64Url(credential.rawId),
        type: credential.type,
        response: {
          attestationObject: toBase64Url(response.attestationObject),
          clientDataJSON: toBase64Url(response.clientDataJSON),
          transports: response.getTransports ? response.getTransports() : [],
        },
        clientExtensionResults: credential.getClientExtensionResults(),
        authenticatorAttachment: credential.authenticatorAttachment,
      };

      await verifyEnrollment(options.challengeId, registrationResponse);
      this.message = "Passkey enrolled.";
      await this.loadCredentials();
    } catch (err) {
      this.error = `Enrollment failed: ${formatEnrollmentError(err)}`;
    } finally {
      this.busy = false;
    }
  };

  private preparePublicKeyOptions(
    options: EnrollmentOptions,
  ): PublicKeyCredentialCreationOptions {
    const publicKey = structuredClone(options) as Record<string, any>;
    publicKey.challenge = fromBase64Url(publicKey.challenge);
    if (publicKey.user?.id) {
      publicKey.user.id = fromBase64Url(publicKey.user.id);
    }
    if (Array.isArray(publicKey.excludeCredentials)) {
      publicKey.excludeCredentials = publicKey.excludeCredentials.map(
        (item: Record<string, unknown>) => ({
          ...item,
          id: fromBase64Url(String(item.id ?? "")),
        }),
      );
    }
    delete publicKey.challengeId;
    return publicKey as PublicKeyCredentialCreationOptions;
  }
}

function fromBase64Url(input: string): ArrayBuffer {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "===".slice((base64.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function toBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function formatEnrollmentError(err: unknown): string {
  if (
    err instanceof DOMException &&
    (err.name === "AbortError" || err.name === "NotAllowedError")
  ) {
    return "Enrollment was cancelled or timed out.";
  }
  if (err instanceof DOMException && err.name === "InvalidStateError") {
    return "This authenticator is already registered.";
  }
  if (err instanceof DOMException && err.name === "SecurityError") {
    return "Invalid origin. Open dashboard on http://localhost and retry.";
  }
  if (err instanceof DOMException && err.name === "NotSupportedError") {
    return "No supported platform authenticator is available.";
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
