import { describe, expect, it } from "vitest";
import { initials, formatDate, formatCount, formatActivity } from "../utils/format";
import { sections } from "../utils/navigation";

describe("display helpers", () => {
  it("formats Vietnamese names safely", () => {
    expect(initials(" Nguyễn Minh An ")).toBe("MA");
    expect(initials(" ")).toBe("U");
    expect(initials()).toBe("U");
  });
  it("handles invalid timestamps", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
    expect(formatDate("2026-11-11T10:00:00Z")).toContain("11/11/2026");
  });
  it("formats real counters including zero", () => {
    expect(formatCount(0)).toBe("0");
    expect(formatCount(1000)).toBe("1.000");
  });
  it("localizes known activities without inventing unknown events", () => {
    expect(formatActivity({ action: "auth.register", description: "Account created" })).toBe("Đã tạo tài khoản");
    expect(formatActivity({ action: "future.action", description: "Original event" })).toBe("Original event");
    expect(formatActivity({ action: "toString", description: "Original event" })).toBe("Original event");
  });
  it("labels all unimplemented modules with an explicit phase", () => {
    expect(Object.keys(sections)).toHaveLength(3);
    for (const section of Object.values(sections)) {
      expect(section.phase).toMatch(/^Phase [2-6]/);
      expect(section.items.length).toBeGreaterThan(0);
    }
  });
});
