import { z } from "zod";

export const ServerConfigSchema = z.object({
  alias: z.string().min(1).regex(/^[a-zA-Z0-9_-]+$/, "Alias must be alphanumeric (with _ and -)"),
  command: z.string().min(1),
  args: z.array(z.string()).optional(),
  env: z.record(z.string()).optional(),
});
export type ServerConfig = z.infer<typeof ServerConfigSchema>;

export const ServersConfigSchema = z.object({
  servers: z.array(ServerConfigSchema).default([]),
});
export type ServersConfig = z.infer<typeof ServersConfigSchema>;
