import { describe, expect, it } from "vitest";

import { formatAppVersion } from "./appVersion";

describe("formatAppVersion", () => {
  it("adds the display prefix to a bare version", () => {
    expect(formatAppVersion("1.0.0")).toBe("V1.0.0");
  });

  it("does not duplicate an existing prefix", () => {
    expect(formatAppVersion("V4.0")).toBe("V4.0");
    expect(formatAppVersion("v2.1")).toBe("V2.1");
  });

  it("handles an empty configuration value", () => {
    expect(formatAppVersion(" ")).toBe("V—");
  });
});
