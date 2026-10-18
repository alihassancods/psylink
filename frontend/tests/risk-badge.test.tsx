import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskBadge } from "@/components/clinician/risk-badge";

/**
 * The safety requirement is that risk never travels as colour alone, so each state is asserted as
 * text + icon + tone class, including the `medium`/`moderate` spelling difference between endpoints.
 */
describe("RiskBadge", () => {
  it("shows the word and an icon for low", () => {
    render(<RiskBadge risk="low" />);
    const badge = screen.getByText("Low").closest("[data-risk]") as HTMLElement;
    expect(badge).toHaveAttribute("data-risk", "low");
    expect(badge.querySelector("svg")).not.toBeNull();
    expect(badge.className).toContain("text-risk-low");
  });

  it("shows the word and an icon for moderate", () => {
    render(<RiskBadge risk="moderate" />);
    const badge = screen.getByText("Moderate").closest("[data-risk]") as HTMLElement;
    expect(badge).toHaveAttribute("data-risk", "moderate");
    expect(badge.querySelector("svg")).not.toBeNull();
    expect(badge.className).toContain("text-risk-moderate");
  });

  it("shows the word and an icon for high", () => {
    render(<RiskBadge risk="high" />);
    const badge = screen.getByText("High").closest("[data-risk]") as HTMLElement;
    expect(badge).toHaveAttribute("data-risk", "high");
    expect(badge.querySelector("svg")).not.toBeNull();
    expect(badge.className).toContain("text-risk-high");
  });

  it("reads the alerts API's `medium` as moderate", () => {
    render(<RiskBadge risk="medium" />);
    const badge = screen.getByText("Moderate").closest("[data-risk]") as HTMLElement;
    expect(badge).toHaveAttribute("data-risk", "moderate");
  });

  it("says so when nothing was analysed, instead of showing no badge", () => {
    render(<RiskBadge risk={null} />);
    const badge = screen.getByText("Not analysed").closest("[data-risk]") as HTMLElement;
    expect(badge).toHaveAttribute("data-risk", "none");
    expect(badge.querySelector("svg")).not.toBeNull();
  });

  it("labels the value for a screen reader", () => {
    const { container } = render(<RiskBadge risk="high" />);
    expect(container.querySelector(".sr-only")?.textContent).toBe("Risk level: ");
  });
});
