import { createDashboardServer } from "../dashboard/dashboard-server.js";
import open from "open";
import path from "node:path";
import { fileURLToPath } from "node:url";

export interface DashboardArgs {
  port: number;
  noOpen: boolean;
}

export function parseDashboardArgs(argv: string[]): DashboardArgs {
  let port = 2222;
  let noOpen = false;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--no-open") {
      noOpen = true;
      continue;
    }
    if (arg.startsWith("--port=")) {
      port = parsePort(arg.slice("--port=".length));
      continue;
    }
    if (arg === "--port") {
      const next = argv[i + 1];
      if (!next) throw new Error("Missing value for --port");
      port = parsePort(next);
      i += 1;
      continue;
    }
  }

  return { port, noOpen };
}

function parsePort(raw: string): number {
  if (!/^\d+$/.test(raw)) {
    throw new Error(`Invalid --port value: ${raw}`);
  }
  const port = Number.parseInt(raw, 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`Port out of range: ${raw}`);
  }
  return port;
}

export async function main(argv: string[] = process.argv.slice(2)): Promise<void> {
  const { port, noOpen } = parseDashboardArgs(argv);
  const app = await createDashboardServer({ port });
  await app.listen({ port, host: "127.0.0.1" });
  process.stderr.write(`Dashboard running at http://127.0.0.1:${port}\n`);
  if (!noOpen) {
    await open(`http://127.0.0.1:${port}`);
  }
}

const isDirectRun =
  process.argv[1] !== undefined &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isDirectRun) {
  main().catch((err) => {
    process.stderr.write(`Dashboard CLI error: ${err}\n`);
    process.exit(1);
  });
}
