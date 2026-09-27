import { describe, expect, it } from "vitest";

import { formatUsdc } from "./format";

describe("formatUsdc", () => {
  it("converts 6-decimal base units to a dollar string", () => {
    expect(formatUsdc(20_000000)).toBe("$20.00");
  });

  it("handles fractional cents correctly", () => {
    expect(formatUsdc(1_500000)).toBe("$1.50");
  });

  it("handles zero", () => {
    expect(formatUsdc(0)).toBe("$0.00");
  });
});
