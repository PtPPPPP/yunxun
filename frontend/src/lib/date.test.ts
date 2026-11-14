import { describe, expect, it } from "vitest";

import { addDays, toIsoDate } from "./date";

describe("本地日期工具", () => {
  it("按本地时间取日期，晚间不会被换算成前一天或后一天", () => {
    expect(toIsoDate(new Date(2026, 0, 5, 23, 30))).toBe("2026-01-05");
    expect(toIsoDate(new Date(2026, 0, 5, 0, 30))).toBe("2026-01-05");
  });

  it("跨月、跨年加减天数", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2024-02-28", 1)).toBe("2024-02-29");
  });
});
