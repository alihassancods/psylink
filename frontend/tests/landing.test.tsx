import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LandingNav } from "@/components/landing/nav";
import { Hero } from "@/components/landing/hero";
import { Faq } from "@/components/landing/faq";
import { ProblemCards } from "@/components/landing/problem-cards";
import { Steps } from "@/components/landing/steps";
import { AudienceColumns } from "@/components/landing/audience-columns";
import { SafetySection } from "@/components/landing/safety-section";
import { DemoCta } from "@/components/landing/demo-cta";
import { LandingFooter } from "@/components/landing/footer";
import {
  audiences,
  demoButtons,
  demoCta,
  faq,
  hero,
  heroVisual,
  howItWorks,
  nav,
  problem,
  product,
  safety,
} from "@/app/(landing)/content";
import type { AuthMe } from "@/types/api";

/**
 * Landing page tests, limited to what can actually break silently: the copy rules the product
 * depends on, the demo buttons reaching the shared login helper, and the nav offering the dashboard
 * to someone already signed in. Layout and styling are checked in a browser, not here.
 */

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  demoLogin: vi.fn(),
  session: {
    status: "anonymous" as "anonymous" | "loading" | "authenticated",
    profile: null as AuthMe | null,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: React.PropsWithChildren<{ href: string }>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/auth/session-provider", () => ({
  HOME_BY_ROLE: { patient: "/home", clinician: "/patients" },
  PATIENT_LANDING: "/home",
  useSession: () => ({
    status: mocks.session.status,
    profile: mocks.session.profile,
    hasSession: mocks.session.status === "authenticated",
    notice: null,
    demoLogin: mocks.demoLogin,
    signIn: vi.fn(),
    signUpPatient: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
  }),
}));

afterEach(() => {
  mocks.replace.mockReset();
  mocks.demoLogin.mockReset();
  mocks.session.status = "anonymous";
  mocks.session.profile = null;
});

function AllSections() {
  return (
    <>
      <Hero />
      <ProblemCards />
      <Steps />
      <AudienceColumns />
      <SafetySection />
      <DemoCta />
      <Faq />
      <LandingFooter />
    </>
  );
}

describe("landing copy rules", () => {
  it("renders every section heading at the right level", () => {
    render(<AllSections />);

    expect(screen.getByRole("heading", { level: 1, name: hero.heading })).toBeInTheDocument();
    for (const name of [
      problem.heading,
      howItWorks.heading,
      ...audiences.columns.map((column) => column.heading),
      safety.heading,
      demoCta.heading,
      faq.heading,
    ]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("states the limits directly under the hero buttons", () => {
    const { container } = render(<Hero />);

    const notice = screen.getByText(hero.notice);
    const [firstButton] = screen.getAllByRole("button");
    // DOM order is visual order here: the notice has to come after the buttons, not in the footer.
    expect(
      notice.compareDocumentPosition(firstButton) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
    expect(container.textContent).toContain("Not emergency care");
  });

  it("never uses the internal role name, and never claims monitoring", () => {
    const { container } = render(<AllSections />);
    const text = container.textContent ?? "";

    // "clinician" is the database role; a visitor reads "psychologist or psychiatrist".
    expect(text).not.toMatch(/clinician/i);
    expect(text).not.toMatch(/real-?time monitor/i);
    expect(text).not.toMatch(/monitors you/i);
    // Diagnosing is never claimed; saying it does not diagnose is required copy, so the word
    // itself is allowed only in the negated forms the spec asks for.
    for (const match of text.match(/diagnos\w*/gi) ?? []) {
      const sentence = text.slice(Math.max(0, text.indexOf(match) - 24), text.indexOf(match));
      expect(sentence, match).toMatch(/\b(no|not)\b/i);
    }
  });

  it("keeps the FAQ answers honest about validation and about alerts", () => {
    const { container } = render(<Faq />);
    expect(container.textContent).toContain("Not yet. Psylink is a hackathon prototype");
    expect(container.textContent).toContain("are not real-time and are not a substitute");
    expect(container.textContent).toContain(
      "Only the psychologist or psychiatrist you link",
    );
  });

  it("links the footer to the repository and repeats the disclaimer", () => {
    render(<LandingFooter />);
    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", product.githubUrl);
    expect(screen.getByText(product.disclaimer)).toBeInTheDocument();
    expect(screen.getByText(product.event)).toBeInTheDocument();
  });

  it("keeps a target on the page for every in-page nav link", () => {
    const { container } = render(<AllSections />);
    const anchors = new Set(
      Array.from(container.querySelectorAll("section[id]")).map((node) => `#${node.id}`),
    );
    for (const link of nav.links) {
      if (!("external" in link && link.external)) {
        expect(anchors, `${link.label} -> ${link.href}`).toContain(link.href);
      }
    }
  });
});

describe("demo buttons", () => {
  it("signs in as the patient through the shared helper and routes to /home", async () => {
    const user = userEvent.setup();
    mocks.demoLogin.mockResolvedValue({ id: "p1", role: "patient", display_name: "Ada" });
    render(<Hero />);

    await user.click(screen.getByRole("button", { name: demoButtons.patientLabel }));

    await waitFor(() => expect(mocks.demoLogin).toHaveBeenCalledWith("patient"));
    expect(mocks.replace).toHaveBeenCalledWith("/home");
  });

  it("signs in as the psychologist and routes to the patient queue", async () => {
    const user = userEvent.setup();
    mocks.demoLogin.mockResolvedValue({ id: "c1", role: "clinician", display_name: "Dr" });
    render(<DemoCta />);

    await user.click(screen.getByRole("button", { name: demoButtons.psychologistLabel }));

    await waitFor(() => expect(mocks.demoLogin).toHaveBeenCalledWith("clinician"));
    expect(mocks.replace).toHaveBeenCalledWith("/patients");
  });

  it("says what it is doing while the demo wakes up", async () => {
    const user = userEvent.setup();
    let release: (value: unknown) => void = () => {};
    mocks.demoLogin.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    render(<Hero />);

    await user.click(screen.getByRole("button", { name: demoButtons.patientLabel }));

    // A cold free-tier backend can take a minute; a pressed button that still says "Try as
    // patient" reads as a dead page.
    expect(screen.getByRole("button", { name: demoButtons.waitingLabel })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: demoButtons.psychologistLabel })).toBeDisabled();

    release({ id: "p1", role: "patient", display_name: "Ada" });
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/home"));
  });

  it("shows a friendly failure and a retry that re-runs the same role", async () => {
    const user = userEvent.setup();
    mocks.demoLogin.mockRejectedValue(new Error("cold start"));
    render(<Hero />);

    await user.click(screen.getByRole("button", { name: demoButtons.patientLabel }));

    expect(await screen.findByRole("alert")).toHaveTextContent(demoButtons.errorNote);
    expect(mocks.demoLogin).toHaveBeenCalledTimes(1);

    mocks.demoLogin.mockResolvedValue({ id: "p1", role: "patient", display_name: "Ada" });
    await user.click(screen.getByRole("button", { name: demoButtons.retryLabel }));

    await waitFor(() => expect(mocks.demoLogin).toHaveBeenCalledTimes(2));
    expect(mocks.demoLogin).toHaveBeenLastCalledWith("patient");
  });
});

describe("nav session state", () => {
  it("offers the demo to a visitor with no session", () => {
    render(<LandingNav />);
    expect(screen.getByRole("link", { name: nav.ctaLabel })).toHaveAttribute("href", "#demo");
    expect(screen.queryByText(nav.dashboardLabel)).not.toBeInTheDocument();
  });

  it("keeps the demo CTA visible while the session is still resolving", () => {
    // Swapping to a spinner here would hide the page's only action from every visitor.
    mocks.session.status = "loading";
    render(<LandingNav />);
    expect(screen.getByRole("link", { name: nav.ctaLabel })).toBeInTheDocument();
  });

  it("swaps to the dashboard for the signed-in role", () => {
    mocks.session.status = "authenticated";
    mocks.session.profile = { id: "p1", role: "patient", display_name: "Ada" };
    const { unmount } = render(<LandingNav />);
    expect(screen.getByRole("link", { name: nav.dashboardLabel })).toHaveAttribute("href", "/home");
    expect(screen.queryByText(nav.ctaLabel)).not.toBeInTheDocument();
    unmount();

    mocks.session.profile = { id: "c1", role: "clinician", display_name: "Dr" };
    render(<LandingNav />);
    expect(screen.getByRole("link", { name: nav.dashboardLabel })).toHaveAttribute(
      "href",
      "/patients",
    );
  });
});

describe("FAQ", () => {
  it("is built from native details/summary, which is what makes it keyboard-operable", async () => {
    const user = userEvent.setup();
    render(<Faq />);

    const question = screen.getByText(faq.items[0].question);
    expect(question.tagName).toBe("SUMMARY");
    expect(question.closest("details")).not.toBeNull();

    await user.tab();
    expect(question).toHaveFocus();
  });

  it("keeps every question and answer in the document, open or closed", () => {
    const { container } = render(<Faq />);
    for (const item of faq.items) {
      expect(screen.getByText(item.question)).toBeInTheDocument();
      expect(container.textContent).toContain(item.answer);
    }
  });
});

describe("decorative visuals", () => {
  it("hides the mockups from assistive tech and gives each a sentence instead", () => {
    const { container } = render(<Hero />);

    expect(container.querySelectorAll("svg[aria-hidden='true']").length).toBeGreaterThan(0);
    expect(screen.getByText(heroVisual.phone.srOnly)).toBeInTheDocument();
    expect(screen.getByText(heroVisual.trend.srOnly)).toBeInTheDocument();
  });
});
