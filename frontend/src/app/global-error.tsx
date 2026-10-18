"use client";

/**
 * Root error boundary. `global-error.tsx` replaces <html> and <body> and does not inherit
 * globals.css, so the styles here are inline and the copy is deliberately plain.
 */
export default function GlobalError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="en">
      <body style={{ background: "#f8fafc", color: "#0f172a", fontFamily: "system-ui, sans-serif", padding: 24 }}>
        <h1 style={{ fontSize: 18 }}>Psylink hit a problem</h1>
        <p style={{ color: "#475569" }}>
          Nothing you submitted is lost. Reloading usually fixes this.
        </p>
        <button
          type="button"
          onClick={retry}
          style={{
            minHeight: 44,
            padding: "8px 16px",
            borderRadius: 8,
            border: "1px solid #0f766e",
            background: "#0f766e",
            color: "#ffffff",
            fontSize: 14,
          }}
        >
          Reload
        </button>
      </body>
    </html>
  );
}
