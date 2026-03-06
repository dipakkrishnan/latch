import fs from "node:fs";
import path from "node:path";

const CRED_DIR =
  process.env.AGENT_2FA_DIR ??
  path.join(process.env.HOME ?? process.env.USERPROFILE ?? "~", ".agent-2fa");
const CRED_PATH = path.join(CRED_DIR, "credentials.json");

export interface StoredCredential {
  credentialID: string;       // base64url
  publicKey: string;          // base64
  counter: number;
  transports?: string[];
  createdAt: string;
}

export function loadCredentials(): StoredCredential[] {
  if (!fs.existsSync(CRED_PATH)) return [];
  const raw = fs.readFileSync(CRED_PATH, "utf-8");
  return JSON.parse(raw) as StoredCredential[];
}

export function saveCredential(cred: StoredCredential): void {
  const existing = loadCredentials();
  existing.push(cred);
  saveCredentials(existing);
}

export function saveCredentials(credentials: StoredCredential[]): void {
  fs.mkdirSync(CRED_DIR, { recursive: true });
  fs.writeFileSync(CRED_PATH, JSON.stringify(credentials, null, 2), "utf-8");
}

export function deleteCredential(credentialID: string): boolean {
  const existing = loadCredentials();
  const next = existing.filter((cred) => cred.credentialID !== credentialID);
  if (next.length === existing.length) return false;
  saveCredentials(next);
  return true;
}

export function updateCredentialCounter(
  credentialID: string,
  counter: number,
): boolean {
  const existing = loadCredentials();
  const target = existing.find((cred) => cred.credentialID === credentialID);
  if (!target) return false;
  target.counter = counter;
  saveCredentials(existing);
  return true;
}
