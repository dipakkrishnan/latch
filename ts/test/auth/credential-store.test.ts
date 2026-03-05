import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type CredentialStoreModule = typeof import("../../src/auth/credential-store.js");

describe("credential-store", () => {
  const originalDataDir = process.env.AGENT_2FA_DIR;
  let tempHome = "";
  let tempDataDir = "";
  let store: CredentialStoreModule;

  beforeEach(async () => {
    tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "agent-2fa-cred-"));
    tempDataDir = path.join(tempHome, ".agent-2fa");
    process.env.AGENT_2FA_DIR = tempDataDir;
    vi.resetModules();
    store = await import("../../src/auth/credential-store.js");
  });

  afterEach(() => {
    process.env.AGENT_2FA_DIR = originalDataDir;
    fs.rmSync(tempHome, { recursive: true, force: true });
  });

  it("deletes an existing credential", () => {
    store.saveCredential({
      credentialID: "cred-1",
      publicKey: "pub1",
      counter: 1,
      createdAt: "2026-01-01T00:00:00.000Z",
    });
    store.saveCredential({
      credentialID: "cred-2",
      publicKey: "pub2",
      counter: 2,
      createdAt: "2026-01-02T00:00:00.000Z",
    });

    const deleted = store.deleteCredential("cred-1");

    expect(deleted).toBe(true);
    expect(store.loadCredentials()).toEqual([
      {
        credentialID: "cred-2",
        publicKey: "pub2",
        counter: 2,
        createdAt: "2026-01-02T00:00:00.000Z",
      },
    ]);
  });

  it("returns false when deleting a missing credential", () => {
    store.saveCredential({
      credentialID: "cred-1",
      publicKey: "pub1",
      counter: 1,
      createdAt: "2026-01-01T00:00:00.000Z",
    });

    const deleted = store.deleteCredential("missing");

    expect(deleted).toBe(false);
    expect(store.loadCredentials()).toHaveLength(1);
  });

  it("updates a credential counter and persists it", () => {
    store.saveCredential({
      credentialID: "cred-1",
      publicKey: "pub1",
      counter: 1,
      createdAt: "2026-01-01T00:00:00.000Z",
    });

    const updated = store.updateCredentialCounter("cred-1", 42);

    expect(updated).toBe(true);
    expect(store.loadCredentials()[0].counter).toBe(42);
  });
});
