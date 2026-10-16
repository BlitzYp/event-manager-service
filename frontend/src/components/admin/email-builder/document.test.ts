import { describe, expect, it } from "vitest";
import { defaultBlock, sampleHtml, starterDocument, type BlockType } from "./document";

describe("email document helpers", () => {
  it.each<BlockType>(["Heading", "Text", "Button", "Image", "Divider", "Spacer", "Html"])(
    "creates independent editable defaults for %s",
    (type) => {
      const first = defaultBlock(type);
      const second = defaultBlock(type);
      expect(first.type).toBe(type);
      expect(first).toEqual(second);
      expect(first.data).not.toBe(second.data);
    },
  );

  it("keeps starter layout references connected to existing blocks", () => {
    const childIds = starterDocument.root.data.childrenIds as string[];
    expect(childIds.length).toBeGreaterThan(0);
    for (const childId of childIds) expect(starterDocument[childId]).toBeDefined();
  });

  it("substitutes preview samples rather than real wallet credentials", () => {
    expect(sampleHtml("Hello {{participant_name}}: {{wallet_link}}"))
      .toBe("Hello Anna Bērziņa: https://example.com/wallet");
  });
});
