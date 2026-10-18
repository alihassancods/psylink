import { SkipLink } from "@/components/layout/skip-link";
import { hero, product } from "@/app/(landing)/content";

/**
 * Public landing page. Composed here; each section is its own small component under
 * `src/components/landing/`. Server components throughout, with client islands only where a click
 * or a session check is genuinely needed.
 */
export default function LandingPage() {
  return (
    <>
      <SkipLink href="#main" />
      <main id="main">
        <h1>{hero.heading}</h1>
        <p>{hero.subhead}</p>
        <p>{hero.notice}</p>
        <p>{product.tagline}</p>
      </main>
    </>
  );
}
