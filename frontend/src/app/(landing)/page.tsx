import { LandingNav } from "@/components/landing/nav";
import { Hero } from "@/components/landing/hero";
import { SkipLink } from "@/components/layout/skip-link";

/**
 * Public landing page. Composed here; each section is its own small component under
 * `src/components/landing/`. Server components throughout, with client islands only where a click
 * or a session check is genuinely needed — the nav and the demo buttons.
 */
export default function LandingPage() {
  return (
    <>
      <SkipLink href="#main" />
      <LandingNav />
      <main id="main">
        <Hero />
      </main>
    </>
  );
}
