import { describe, it, expect } from "vitest";
import { extractJson } from "@/lib/integrations/search";

describe("extractJson", () => {
  it("parses pure JSON object", () => {
    expect(extractJson('{"a":1,"b":"two"}')).toEqual({ a: 1, b: "two" });
  });

  it("parses pure JSON array", () => {
    expect(extractJson("[1, 2, 3]")).toEqual([1, 2, 3]);
  });

  it("tolerates surrounding whitespace", () => {
    expect(extractJson("\n\n  { \"a\": 1 }  \n")).toEqual({ a: 1 });
  });

  it("unwraps a ```json ... ``` fence", () => {
    const text = "Here you go:\n```json\n{\"hits\":[{\"url\":\"https://example.com\"}]}\n```\nLet me know.";
    expect(extractJson(text)).toEqual({ hits: [{ url: "https://example.com" }] });
  });

  it("unwraps a bare ``` ... ``` fence", () => {
    const text = "```\n[1,2,3]\n```";
    expect(extractJson(text)).toEqual([1, 2, 3]);
  });

  it("extracts the first balanced object from prose", () => {
    const text = 'Final answer below.\nThe result is {"slug":"r770","ok":true} — please review.';
    expect(extractJson(text)).toEqual({ slug: "r770", ok: true });
  });

  it("handles nested braces inside strings", () => {
    const text = 'Prefix... {"note":"this } looks tricky","n":1} suffix';
    expect(extractJson(text)).toEqual({ note: "this } looks tricky", n: 1 });
  });

  it("handles escaped quotes inside strings", () => {
    const text = '{"q":"she said \\"hi\\""}';
    expect(extractJson(text)).toEqual({ q: 'she said "hi"' });
  });

  it("throws a useful error when no JSON is present", () => {
    expect(() => extractJson("just prose, nothing structured")).toThrow(/no parseable JSON/);
  });

  it("error message includes the first 200 chars for debugging", () => {
    const longProse = "X".repeat(500);
    try {
      extractJson(longProse);
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as Error).message).toContain("X".repeat(200));
    }
  });
});