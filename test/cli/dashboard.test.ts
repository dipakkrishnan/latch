import { describe, expect, it } from "vitest";
import { parseDashboardArgs } from "../../src/cli/dashboard.js";

describe("dashboard CLI args", () => {
  it("uses defaults when no args provided", () => {
    expect(parseDashboardArgs([])).toEqual({
      port: 2222,
      noOpen: false,
    });
  });

  it("parses --port=NNN", () => {
    expect(parseDashboardArgs(["--port=3000"])).toEqual({
      port: 3000,
      noOpen: false,
    });
  });

  it("parses --port NNN and --no-open", () => {
    expect(parseDashboardArgs(["--port", "4444", "--no-open"])).toEqual({
      port: 4444,
      noOpen: true,
    });
  });

  it("throws on missing --port value", () => {
    expect(() => parseDashboardArgs(["--port"])).toThrow(
      "Missing value for --port",
    );
  });

  it("throws on invalid port value", () => {
    expect(() => parseDashboardArgs(["--port=abc"])).toThrow(
      "Invalid --port value: abc",
    );
  });

  it("throws on out-of-range port", () => {
    expect(() => parseDashboardArgs(["--port=70000"])).toThrow(
      "Port out of range: 70000",
    );
  });
});

