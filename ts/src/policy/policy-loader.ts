import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";
import { PolicyConfigSchema, type PolicyConfig } from "./policy-types.js";

const POLICY_DIR =
  process.env.AGENT_2FA_DIR ??
  path.join(process.env.HOME ?? process.env.USERPROFILE ?? "~", ".agent-2fa");
const POLICY_PATH = path.join(POLICY_DIR, "policy.yaml");

const DEFAULT_POLICY = `# agent-2fa policy configuration
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
`;

let cached: PolicyConfig | null = null;

/**
 * Load and validate the policy from ~/.agent-2fa/policy.yaml.
 * Creates the default policy file if it doesn't exist.
 */
export function loadPolicy(forceReload = false): PolicyConfig {
  if (cached && !forceReload) return cached;

  if (!fs.existsSync(POLICY_PATH)) {
    fs.mkdirSync(POLICY_DIR, { recursive: true });
    fs.writeFileSync(POLICY_PATH, DEFAULT_POLICY, "utf-8");
  }

  const raw = fs.readFileSync(POLICY_PATH, "utf-8");
  const parsed = parseYaml(raw);
  cached = PolicyConfigSchema.parse(parsed);
  return cached;
}

/**
 * Load policy from an arbitrary YAML string (useful for testing).
 */
export function loadPolicyFromString(yaml: string): PolicyConfig {
  const parsed = parseYaml(yaml);
  return PolicyConfigSchema.parse(parsed);
}

export function clearCache(): void {
  cached = null;
}

/**
 * Validate and persist policy to ~/.agent-2fa/policy.yaml.
 */
export function savePolicy(config: PolicyConfig): void {
  const parsed = PolicyConfigSchema.parse(config);
  fs.mkdirSync(POLICY_DIR, { recursive: true });
  fs.writeFileSync(POLICY_PATH, stringifyYaml(parsed), "utf-8");
  cached = parsed;
}
