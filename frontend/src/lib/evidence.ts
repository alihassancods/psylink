/**
 * Where the model's evidence quote sits in what the patient actually said.
 *
 * The backend guarantees `evidence_quote` is a verbatim substring of the analysed text, but the
 * analysed text can be `transcript + "\n" + note`, and no offsets are served. So: honour offsets if
 * a future response includes them, otherwise find the quote exactly, then tolerate whitespace and
 * case differences (which the browser's own rendering would hide anyway), and finally give up
 * visibly rather than highlighting a near-match silently.
 */

export interface HighlightSegment {
  text: string;
  highlighted: boolean;
}

export interface EvidenceOffsets {
  start: number;
  end: number;
}

export interface HighlightResult {
  segments: HighlightSegment[];
  matched: boolean;
  /** Which field the quote was found in, when it was found. */
  field: "transcript" | "note" | null;
}

function normalizeWithMap(text: string) {
  let normalized = "";
  const map: number[] = [];
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (/\s/.test(character)) {
      if (normalized.length > 0 && !normalized.endsWith(" ")) {
        normalized += " ";
        map.push(index);
      }
      continue;
    }
    normalized += character.toLowerCase();
    map.push(index);
  }
  return { normalized, map };
}

function findInText(text: string, quote: string): EvidenceOffsets | null {
  const exact = text.indexOf(quote);
  if (exact >= 0) return { start: exact, end: exact + quote.length };

  const haystack = normalizeWithMap(text);
  const needle = normalizeWithMap(quote.trim()).normalized.trim();
  if (!needle) return null;

  const at = haystack.normalized.indexOf(needle);
  if (at < 0) return null;

  const lastSourceIndex = haystack.map[at + needle.length - 1];
  if (lastSourceIndex === undefined) return null;
  return { start: haystack.map[at], end: lastSourceIndex + 1 };
}

function splitAt(text: string, offsets: EvidenceOffsets): HighlightSegment[] {
  return [
    { text: text.slice(0, offsets.start), highlighted: false },
    { text: text.slice(offsets.start, offsets.end), highlighted: true },
    { text: text.slice(offsets.end), highlighted: false },
  ].filter((segment) => segment.text.length > 0);
}

export function highlightEvidence(
  text: string | null | undefined,
  quote: string | null | undefined,
  offsets?: EvidenceOffsets | null,
): HighlightResult {
  const empty: HighlightResult = { segments: [{ text: text ?? "", highlighted: false }], matched: false, field: null };
  if (!text) return { segments: [], matched: false, field: null };

  // Offsets win when they agree with the quote, because they are what the model was shown.
  if (offsets && offsets.start >= 0 && offsets.end > offsets.start && offsets.end <= text.length) {
    const sliced = text.slice(offsets.start, offsets.end);
    const agrees = !quote || sliced.trim().toLowerCase() === quote.trim().toLowerCase();
    if (agrees) return { segments: splitAt(text, offsets), matched: true, field: "transcript" };
  }

  if (!quote || !quote.trim()) return empty;

  const found = findInText(text, quote);
  if (!found) return empty;
  return { segments: splitAt(text, found), matched: true, field: "transcript" };
}

/**
 * The analysed text may be the transcript and a typed note joined by a newline. Search both and
 * report which one holds the quote, so the highlight lands on real words.
 */
export function highlightEvidenceAcross(
  fields: { transcript?: string | null; note?: string | null },
  quote: string | null | undefined,
  offsets?: EvidenceOffsets | null,
): { transcript: HighlightResult; note: HighlightResult; matched: boolean } {
  const transcript = highlightEvidence(fields.transcript, quote, offsets);
  // Offsets refer to the joined text, so only the transcript can use them; the note falls back
  // to a quote search.
  const note = highlightEvidence(fields.note, quote, null);
  return { transcript, note, matched: transcript.matched || note.matched };
}
