import { createDashboardServer } from "../dashboard/dashboard-server.js";
import open from "open";

const portArg = process.argv.find((a) => a.startsWith("--port="));
const port = parseInt(portArg?.split("=")[1] ?? "2222", 10);

const app = await createDashboardServer({ port });
await app.listen({ port, host: "127.0.0.1" });

process.stderr.write(`Dashboard running at http://127.0.0.1:${port}\n`);
await open(`http://127.0.0.1:${port}`);
