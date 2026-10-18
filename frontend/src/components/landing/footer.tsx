import Link from "next/link";

import { footer, product } from "@/app/(landing)/content";
import { Container } from "@/components/landing/section";

/**
 * The last word is the limit, not a slogan: what this is not appears here and, more importantly,
 * under the hero buttons where a visitor cannot miss it.
 */
export function LandingFooter() {
  return (
    <footer className="mt-auto border-t border-border bg-card py-10">
      <Container>
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <p className="text-sm font-semibold text-foreground">{product.name}</p>
            <p className="text-sm text-muted-foreground">{product.tagline}</p>
            <p className="text-sm text-muted-foreground">{product.event}</p>
          </div>

          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-x-6 gap-y-2">
              {footer.links.map((link) => (
                <li key={link.label}>
                  {"external" in link && link.external ? (
                    <a
                      href={link.href}
                      rel="noopener noreferrer"
                      target="_blank"
                      className="inline-flex min-h-11 items-center text-sm text-muted-foreground hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  ) : (
                    <Link
                      href={link.href}
                      className="inline-flex min-h-11 items-center text-sm text-muted-foreground hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <p className="mt-8 text-sm text-muted-foreground">{product.disclaimer}</p>
      </Container>
    </footer>
  );
}
