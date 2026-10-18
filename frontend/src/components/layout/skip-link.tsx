/** Shared accessible skip link for both app shells. */
export function SkipLink({ href = "#main" }: { href?: string }) {
  return (
    <a
      href={href}
      className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:min-h-11 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary focus:shadow-lg focus:outline focus:outline-2 focus:outline-ring"
    >
      Skip to content
    </a>
  );
}
