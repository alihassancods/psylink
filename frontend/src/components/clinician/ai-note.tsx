import { cn } from "@/lib/utils";

/** Required wording wherever model output is shown to a clinician. */
export function AiNote({ className }: { className?: string }) {
  return (
    <p
      className={cn(
        "rounded-lg border border-border bg-muted px-3 py-2 text-xs text-muted-foreground",
        className,
      )}
    >
      AI-generated, verify with the patient. These are descriptions of what the patient said, not an
      assessment or a diagnosis.
    </p>
  );
}
