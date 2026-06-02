import { describe, it, expect } from "vitest";
import { parseMarkdown } from "@/lib/safe-matter";

describe("parseMarkdown — happy path (valid YAML frontmatter)", () => {
  it("parses scalar frontmatter and returns the body separately", () => {
    const raw = `---
title: Dell PowerEdge R770
vendor: dell
slug: r770
---

# Body

Some markdown content.
`;
    const { data, content } = parseMarkdown(raw);
    expect(data.title).toBe("Dell PowerEdge R770");
    expect(data.vendor).toBe("dell");
    expect(data.slug).toBe("r770");
    expect(content).toContain("# Body");
    expect(content).not.toContain("title:");
  });

  it("normalizes Date values to YYYY-MM-DD strings", () => {
    const raw = `---
revised: 2026-05-19
---
body
`;
    const { data } = parseMarkdown(raw);
    expect(data.revised).toBe("2026-05-19");
    expect(typeof data.revised).toBe("string");
  });

  it("normalizes dates nested inside arrays", () => {
    const raw = `---
sources:
  - local: a.pdf
    date: 2024-01-15
  - local: b.pdf
    date: 2025-06-30
---
content
`;
    const { data } = parseMarkdown(raw);
    expect(data.sources[0].date).toBe("2024-01-15");
    expect(data.sources[1].date).toBe("2025-06-30");
  });

  it("returns empty data and the raw body when there's no frontmatter", () => {
    const raw = "no frontmatter here\njust body\n";
    const { data, content } = parseMarkdown(raw);
    expect(data).toEqual({});
    expect(content).toBe(raw);
  });
});

describe("parseMarkdown — fallback path (YAML choked)", () => {
  it("recovers top-level scalars when YAML fails on unquoted braces", () => {
    // Unquoted {curly} confuses js-yaml. The fallback line-by-line parser
    // should still pull out the scalar keys.
    const raw = `---
title: Has {curly} chars that break YAML
slug: thing
---
body lives here
`;
    const { data, content } = parseMarkdown(raw);
    expect(data.slug).toBe("thing");
    expect(content).toContain("body lives here");
  });

  it("strips matched surrounding quotes in fallback", () => {
    const raw = `---
title: "Quoted Value"
other: 'single-quoted'
broken: {bad}
---
body
`;
    const { data } = parseMarkdown(raw);
    // We can't assume which path ran, but quoted scalars must come back unquoted either way.
    expect(data.title).toBe("Quoted Value");
    expect(data.other).toBe("single-quoted");
  });
});