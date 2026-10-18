import { describe, expect, it } from "vitest";

import { highlightEvidence, highlightEvidenceAcross } from "@/lib/evidence";

const TEXT = "I slept about four hours and the meeting on Tuesday was hard.";

describe("evidence highlighter", () => {
  it("highlights an exact quote", () => {
    const result = highlightEvidence(TEXT, "the meeting on Tuesday was hard");
    expect(result.matched).toBe(true);
    expect(result.segments.filter((segment) => segment.highlighted)).toEqual([
      { text: "the meeting on Tuesday was hard", highlighted: true },
    ]);
    expect(result.segments.map((segment) => segment.text).join("")).toBe(TEXT);
  });

  it("tolerates spacing and case differences without changing the words", () => {
    const source = "I said I felt   anxious\tall day.";
    const result = highlightEvidence(source, "felt anxious all day");
    expect(result.matched).toBe(true);
    // The highlight shows the patient's own characters, not the tidied comparison form.
    expect(result.segments.find((segment) => segment.highlighted)?.text).toBe(
      "felt   anxious\tall day",
    );
    expect(result.segments.map((segment) => segment.text).join("")).toBe(source);
  });

  it("uses offsets when they agree with the quote", () => {
    const result = highlightEvidence(TEXT, "four hours", { start: 14, end: 24 });
    expect(result.matched).toBe(true);
    expect(result.segments.find((segment) => segment.highlighted)?.text).toBe("four hours");
  });

  it("falls back to the quote when offsets point somewhere else", () => {
    const result = highlightEvidence(TEXT, "about four hours", { start: 0, end: 1 });
    expect(result.matched).toBe(true);
    expect(result.segments.find((segment) => segment.highlighted)?.text).toBe("about four hours");
  });

  it("does not highlight a near miss, and says it did not match", () => {
    const result = highlightEvidence(TEXT, "I stopped taking my medication");
    expect(result.matched).toBe(false);
    expect(result.segments.every((segment) => !segment.highlighted)).toBe(true);
    expect(result.segments[0].text).toBe(TEXT);
  });

  it("handles missing quote and missing text", () => {
    expect(highlightEvidence(TEXT, null).matched).toBe(false);
    expect(highlightEvidence("", "anything").segments).toEqual([]);
    expect(highlightEvidence(null, null).matched).toBe(false);
  });

  it("finds the quote in the typed note when it is not in the transcript", () => {
    const result = highlightEvidenceAcross(
      { transcript: "Nothing much to say today.", note: "The appointment went badly." },
      "went badly",
    );
    expect(result.matched).toBe(true);
    expect(result.transcript.matched).toBe(false);
    expect(result.note.segments.find((segment) => segment.highlighted)?.text).toBe("went badly");
  });

  it("refuses out-of-range offsets", () => {
    const result = highlightEvidence(TEXT, undefined, { start: 5, end: 999 });
    expect(result.matched).toBe(false);
  });
});
