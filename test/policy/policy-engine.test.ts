import { describe, it, expect } from "vitest";
import { evaluatePolicy } from "../../src/policy/policy-engine.js";
import { loadPolicyFromString } from "../../src/policy/policy-loader.js";

const YAML_POLICY = `
defaultAction: allow
rules:
  - match:
      tool: "Bash"
    action: ask
  - match:
      tool: "Edit|Write|NotebookEdit"
    action: ask
  - match:
      tool: "Read|Glob|Grep"
    action: allow
  - match:
      tool: "Dangerous.*"
    action: deny
`;

describe("policy-engine", () => {
  const config = loadPolicyFromString(YAML_POLICY);

  it("matches exact tool name", () => {
    const result = evaluatePolicy("Bash", config);
    expect(result.action).toBe("ask");
  });

  it("matches alternation pattern", () => {
    expect(evaluatePolicy("Edit", config).action).toBe("ask");
    expect(evaluatePolicy("Write", config).action).toBe("ask");
    expect(evaluatePolicy("NotebookEdit", config).action).toBe("ask");
  });

  it("matches read tools as allow", () => {
    expect(evaluatePolicy("Read", config).action).toBe("allow");
    expect(evaluatePolicy("Glob", config).action).toBe("allow");
    expect(evaluatePolicy("Grep", config).action).toBe("allow");
  });

  it("matches regex wildcard pattern", () => {
    expect(evaluatePolicy("DangerousTool", config).action).toBe("deny");
    expect(evaluatePolicy("DangerousCommand", config).action).toBe("deny");
  });

  it("falls back to defaultAction for unmatched tools", () => {
    const result = evaluatePolicy("WebFetch", config);
    expect(result.action).toBe("allow");
    expect(result.reason).toContain("Default");
  });

  it("returns reason with matching rule pattern", () => {
    const result = evaluatePolicy("Bash", config);
    expect(result.reason).toContain("Bash");
    expect(result.reason).toContain("ask");
  });

  it("first match wins", () => {
    const yaml = `
defaultAction: deny
rules:
  - match:
      tool: "Bash"
    action: allow
  - match:
      tool: "Bash"
    action: deny
`;
    const cfg = loadPolicyFromString(yaml);
    expect(evaluatePolicy("Bash", cfg).action).toBe("allow");
  });

  it("handles browser and webauthn actions", () => {
    const yaml = `
defaultAction: allow
rules:
  - match:
      tool: "Bash"
    action: browser
  - match:
      tool: "Write"
    action: webauthn
`;
    const cfg = loadPolicyFromString(yaml);
    expect(evaluatePolicy("Bash", cfg).action).toBe("browser");
    expect(evaluatePolicy("Write", cfg).action).toBe("webauthn");
  });

  it("handles empty rules list", () => {
    const cfg = loadPolicyFromString("defaultAction: deny\nrules: []");
    expect(evaluatePolicy("Bash", cfg).action).toBe("deny");
  });

  it("does not partial-match tool names", () => {
    // "Bash" rule should not match "BashExtra"
    expect(evaluatePolicy("BashExtra", config).action).toBe("allow"); // falls through to default
  });
});
