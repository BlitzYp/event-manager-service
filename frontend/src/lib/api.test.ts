import { describe, expect, it } from "vitest";
import { money } from "./api";

describe("money", () => {
  it("formats integer minor units without floating point ledger storage", () => {
    expect(money(1250, "EUR")).toContain("12.50");
  });
});

