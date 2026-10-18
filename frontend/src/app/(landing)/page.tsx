import { LandingNav } from "@/components/landing/nav";
import { Hero } from "@/components/landing/hero";
import { ProblemCards } from "@/components/landing/problem-cards";
import { Steps } from "@/components/landing/steps";
import { AudienceColumns } from "@/components/landing/audience-columns";
import { SafetySection } from "@/components/landing/safety-section";
import { DemoCta } from "@/components/landing/demo-cta";
import { Faq } from "@/components/landing/faq";
import { LandingFooter } from "@/components/landing/footer";
import { SkipLink } from "@/components/layout/skip-link";

/**
 * Public landing page. Composed here; each section is its own small component under
 * `src/components/landing/`, and every word comes from `(landing)/content.ts`.
 *
 * Server components throughout. The two client islands are the nav, which has to know whether a
 * Supabase session exists, and the demo buttons, which have to react to a click.
 */
export default function LandingPage() {
  return (
    <>
      <SkipLink href="#main" />
      <LandingNav />
      <main id="main">
        <Hero />
        <ProblemCards />
        <Steps />
        <AudienceColumns />
        <SafetySection />
        <DemoCta />
        <Faq />
      </main>
      <LandingFooter />
    </>
  );
}
