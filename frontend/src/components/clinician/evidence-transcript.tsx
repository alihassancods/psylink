import { highlightEvidenceAcross, type HighlightResult } from "@/lib/evidence";
import { cn } from "@/lib/utils";

/**
 * Renders the patient's words with the model's evidence quote marked. The transcript is shown
 * exactly as stored; the highlight never rewrites it. When the quote cannot be located, it is
 * printed underneath instead of guessing at a match.
 */
export function EvidenceTranscript({
  transcript,
  note,
  quote,
  offsets,
}: {
  transcript: string | null;
  note: string | null;
  quote: string | null;
  offsets?: { start: number; end: number } | null;
}) {
  const results = highlightEvidenceAcross({ transcript, note }, quote, offsets);

  return (
    <div className="space-y-4">
      {transcript ? (
        <Figure label="What the patient said (voice, approved by them)" result={results.transcript} />
      ) : null}

      {note ? <Figure label="What the patient typed" result={results.note} /> : null}

      {!transcript && !note ? (
        <p className="text-sm text-muted-foreground">
          No words were kept for this check-in.
        </p>
      ) : null}

      {quote && !results.matched ? (
        <blockquote className="rounded-lg border border-border bg-muted p-3 text-sm">
          <p className="text-xs font-medium text-muted-foreground">
            Evidence quote, not located in the stored text
          </p>
          <p className="mt-1 italic">“{quote}”</p>
        </blockquote>
      ) : null}
    </div>
  );
}

function Figure({ label, result }: { label: string; result: HighlightResult }) {
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs font-medium text-muted-foreground">{label}</figcaption>
      <p className="whitespace-pre-wrap rounded-lg border border-border bg-card p-3 text-sm leading-relaxed">
        {result.segments.map((segment, index) =>
          segment.highlighted ? (
            <mark
              key={index}
              className={cn("rounded bg-risk-moderate-surface px-1 text-risk-moderate")}
            >
              {segment.text}
            </mark>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
      </p>
    </figure>
  );
}
