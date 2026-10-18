import { hero } from "@/app/(landing)/content";
import { Container } from "@/components/landing/section";
import { DemoActions } from "@/components/landing/demo-actions";
import { PhoneMockup } from "@/components/landing/phone-mockup";
import { TrendChartMock } from "@/components/landing/trend-chart-mock";

/**
 * The first screen. One idea, one action, and the limits said up front: what this is not appears
 * directly under the buttons rather than being left to the footer, because a mental-health product
 * should not make someone scroll to find out it cannot help them in an emergency.
 */
export function Hero() {
  return (
    <section className="pb-14 pt-12 sm:pb-20 sm:pt-16">
      <Container>
        <div className="max-w-3xl">
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            {hero.heading}
          </h1>
          <p className="mt-5 text-lg text-muted-foreground text-pretty sm:text-xl">
            {hero.subhead}
          </p>

          <DemoActions className="mt-8 max-w-xl" />

          <p className="mt-3 text-sm text-muted-foreground">{hero.notice}</p>
        </div>

        {/* Recorder and trend, side by side from 640px up, stacked below it. */}
        <div className="mt-12 grid gap-6 sm:mt-16 sm:grid-cols-2 sm:items-end lg:mt-20">
          <PhoneMockup />
          <TrendChartMock />
        </div>
      </Container>
    </section>
  );
}
