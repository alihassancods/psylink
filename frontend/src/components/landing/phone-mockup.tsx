import { heroVisual } from "@/app/(landing)/content";

/**
 * A drawn phone, not a photograph: no asset to fetch, nothing to license, and it stays on-message
 * at every width. Decorative by intent — the whole mockup is `aria-hidden` and the sentence in
 * `heroVisual.phone.srOnly` is what a screen reader actually gets, because a picture of a record
 * button tells a listener nothing.
 */
export function PhoneMockup() {
  return (
    <div className="relative">
      <p className="sr-only">{heroVisual.phone.srOnly}</p>

      <div
        aria-hidden="true"
        className="mx-auto w-full max-w-[280px] rounded-[2rem] border border-border bg-card p-3 shadow-sm"
      >
        {/* Phone body */}
        <div className="rounded-[1.5rem] border border-border bg-background px-4 pb-5 pt-3">
          <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-border" />

          <p className="text-xs text-muted-foreground">{heroVisual.phone.label}</p>
          <p className="mt-1 text-sm font-medium text-foreground">{heroVisual.phone.prompt}</p>

          {/* Waveform */}
          <div className="mt-5 flex h-12 items-center justify-between gap-1">
            {BARS.map((height, index) => (
              <span
                key={index}
                className="w-1.5 rounded-full bg-accent/70"
                style={{ height: `${height}%` }}
              />
            ))}
          </div>

          <p className="mt-3 text-center text-sm font-medium tabular-nums text-foreground">
            {heroVisual.phone.seconds}
          </p>

          {/* Record control */}
          <div className="mt-4 flex items-center justify-center gap-4">
            <span className="flex size-14 items-center justify-center rounded-full bg-primary/15">
              <span className="relative flex size-9 items-center justify-center rounded-full bg-primary">
                <span className="psylink-pulse absolute inset-0 rounded-full bg-primary" />
                <span className="size-3 rounded-full bg-primary-foreground" />
              </span>
            </span>
          </div>

          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            {heroVisual.phone.micLabel}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Fixed heights, so the mockup renders identically on server and client and never reflows. */
const BARS = [28, 54, 38, 72, 46, 88, 60, 34, 66, 42, 78, 50, 30, 58, 44, 70, 36, 52, 26, 40];
