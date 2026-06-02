import { describe, it, expect } from "vitest";
import {
  calcCost,
  estimateTokensFromText,
} from "@/lib/integrations/anthropic";

describe("calcCost (Opus 4.7 pricing)", () => {
  it("prices plain input + output with no cache", () => {
    const c = calcCost({ inputTokens: 1_000_000, outputTokens: 1_000_000 });
    // 15 USD/MTok input + 75 USD/MTok output
    expect(c.inputUsd).toBeCloseTo(15, 6);
    expect(c.outputUsd).toBeCloseTo(75, 6);
    expect(c.cacheWriteUsd).toBe(0);
    expect(c.cacheReadUsd).toBe(0);
    expect(c.totalUsd).toBeCloseTo(90, 6);
  });

  it("applies the 50% batch discount across every line", () => {
    const std = calcCost({
      inputTokens: 1_000_000,
      outputTokens: 1_000_000,
      cacheCreationTokens: 1_000_000,
      cacheReadTokens: 1_000_000,
    });
    const batch = calcCost({
      inputTokens: 1_000_000,
      outputTokens: 1_000_000,
      cacheCreationTokens: 1_000_000,
      cacheReadTokens: 1_000_000,
      batch: true,
    });
    expect(batch.totalUsd).toBeCloseTo(std.totalUsd / 2, 6);
  });

  it("uses the 1h cache-write rate by default (2x input)", () => {
    const c = calcCost({ inputTokens: 0, outputTokens: 0, cacheCreationTokens: 1_000_000 });
    // 1h write = 30 USD/MTok
    expect(c.cacheWriteUsd).toBeCloseTo(30, 6);
  });

  it("uses the 5m cache-write rate when requested (1.25x input)", () => {
    const c = calcCost({
      inputTokens: 0,
      outputTokens: 0,
      cacheCreationTokens: 1_000_000,
      cacheTtl: "5m",
    });
    expect(c.cacheWriteUsd).toBeCloseTo(18.75, 6);
  });

  it("prices cache reads at 0.1x input regardless of TTL", () => {
    const c = calcCost({ inputTokens: 0, outputTokens: 0, cacheReadTokens: 1_000_000 });
    expect(c.cacheReadUsd).toBeCloseTo(1.5, 6);
  });

  it("totals the four line items", () => {
    const c = calcCost({
      inputTokens: 100_000,
      outputTokens: 50_000,
      cacheCreationTokens: 200_000,
      cacheReadTokens: 400_000,
    });
    const expected = c.inputUsd + c.outputUsd + c.cacheWriteUsd + c.cacheReadUsd;
    expect(c.totalUsd).toBeCloseTo(expected, 9);
  });
});

describe("estimateTokensFromText", () => {
  it("returns 0 for empty input", () => {
    expect(estimateTokensFromText("")).toBe(0);
  });

  it("ignores extra whitespace", () => {
    expect(estimateTokensFromText("   \n\t  ")).toBe(0);
  });

  it("rounds up via the 1.4 words→tokens ratio", () => {
    // 10 words × 1.4 = 14 tokens
    const text = "one two three four five six seven eight nine ten";
    expect(estimateTokensFromText(text)).toBe(14);
  });

  it("is monotonic — more text never yields fewer tokens", () => {
    const a = estimateTokensFromText("alpha beta gamma");
    const b = estimateTokensFromText("alpha beta gamma delta epsilon");
    expect(b).toBeGreaterThanOrEqual(a);
  });
});