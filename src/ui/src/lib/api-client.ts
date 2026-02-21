import type {
  PolicyConfig,
  StoredCredential,
  AuditEntry,
  AuditStats,
} from "./types.js";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function getPolicy(): Promise<PolicyConfig> {
  return fetchJSON<PolicyConfig>("/api/policy");
}

export async function savePolicy(config: PolicyConfig): Promise<void> {
  await fetchJSON<{ ok: boolean }>("/api/policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export async function getPolicyYaml(): Promise<string> {
  const res = await fetch("/api/policy/yaml");
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `Request failed: ${res.status}`);
  }
  return res.text();
}

export async function validatePolicy(
  config: PolicyConfig,
): Promise<{ valid: boolean; errors?: any[] }> {
  return fetchJSON<{ valid: boolean; errors?: any[] }>("/api/policy/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export async function getCredentials(): Promise<StoredCredential[]> {
  return fetchJSON<StoredCredential[]>("/api/credentials");
}

export async function deleteCredential(id: string): Promise<void> {
  await fetchJSON<{ ok: boolean }>(
    `/api/credentials/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export async function getEnrollOptions(): Promise<any> {
  return fetchJSON<any>("/api/enroll/options");
}

export async function verifyEnrollment(
  challengeId: string,
  response: any,
): Promise<void> {
  await fetchJSON<{ ok: boolean }>("/api/enroll/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challengeId, response }),
  });
}

export async function getAuditLog(
  limit?: number,
  offset?: number,
): Promise<AuditEntry[]> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const qs = params.toString();
  return fetchJSON<AuditEntry[]>(`/api/audit-log${qs ? `?${qs}` : ""}`);
}

export async function getAuditStats(): Promise<AuditStats> {
  return fetchJSON<AuditStats>("/api/audit-log/stats");
}
