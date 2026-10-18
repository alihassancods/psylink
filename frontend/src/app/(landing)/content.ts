/**
 * Every word on the public landing page, in one place.
 *
 * Copy rules this file is written against, and that any edit here should keep:
 * - Say "psychologist or psychiatrist" or "your care team". The word "clinician" is an internal
 *   role name and never appears in visitor-facing text.
 * - No claim of diagnosis, treatment, or real-time monitoring. The crisis line sits under the hero
 *   buttons, not only in the footer.
 * - Only features that actually work in this build are described, and the demo says plainly that its
 *   data is synthetic.
 */

export const product = {
  name: "Psylink",
  tagline: "Your voice, between sessions",
  /** Source repository, used by the nav and footer links. */
  githubUrl: "https://github.com/alihassancods/psylink",
  event: "Built for HealthHack 48",
  disclaimer: "Not medical advice. Not emergency care.",
} as const;

export const nav = {
  links: [
    { label: "How it works", href: "#how" },
    { label: "Safety", href: "#safety" },
    { label: "FAQ", href: "#faq" },
    { label: "GitHub", href: product.githubUrl, external: true },
  ],
  ctaLabel: "Try demo",
  dashboardLabel: "Go to dashboard",
} as const;

export const hero = {
  heading: "Your voice, between sessions.",
  subhead:
    "Record a one-minute check-in. Your psychologist or psychiatrist sees how your week went before your next visit.",
  /** Stated directly under the buttons, so nobody has to reach the footer for it. */
  notice: "Not emergency care. Demo data is synthetic.",
} as const;

/**
 * Decorative mockups only. `srOnly` is the text alternative for each visual, because a picture of a
 * recorder says nothing to a screen reader.
 */
export const heroVisual = {
  phone: {
    srOnly: "A phone screen showing a one-minute check-in being recorded.",
    label: "Today's check-in",
    prompt: "How has this week been?",
    seconds: "0:42",
    micLabel: "Recording",
    stopLabel: "Stop",
  },
  trend: {
    srOnly:
      "A synthetic mood trend over fourteen days, dipping midweek and recovering at the end.",
    label: "Mood over 14 days",
    caption: "Demo data",
  },
} as const;

export const problem = {
  heading: "An appointment is an hour. The week is 167.",
  cards: [
    {
      audience: "For patients",
      text: "It's hard to remember, or explain, how the week really felt.",
    },
    {
      audience: "For psychologists and psychiatrists",
      text: "No view of the days in between, and no early sign when things get harder.",
    },
  ],
} as const;

export const howItWorks = {
  id: "how",
  heading: "How it works",
  /** `icon` names a lucide glyph, resolved in the component so this file stays plain data. */
  steps: [
    {
      icon: "mic",
      title: "Speak",
      text: "record a one-minute check-in.",
    },
    {
      icon: "pencil",
      title: "Review",
      text: "edit the transcript before you send it.",
    },
    {
      icon: "chart",
      title: "Analyze",
      text: "a summary and symptom patterns, with no diagnosis.",
    },
    {
      icon: "calendar",
      title: "Prepare",
      text: "your provider sees trends and flagged moments before your visit.",
    },
  ],
} as const;

export const audiences = {
  /**
   * `text` is the sentence as it must appear. `lead` is the part set in medium weight — a substring
   * of `text`, so the two can never disagree and the copy stays exactly what it reads.
   */
  columns: [
    {
      heading: "For patients",
      points: [
        { lead: "Quick", text: "Quick: talk instead of typing" },
        { lead: "In control", text: "In control: you choose to share, and can revoke any time" },
        { lead: "Supported", text: "Supported: crisis resources appear when you need them" },
      ],
    },
    {
      heading: "For psychologists and psychiatrists",
      points: [
        { lead: "Trends", text: "Trends over 7, 14, or 30 days" },
        { lead: "Every flag", text: "Every flag shows the patient's own words" },
        { lead: "Alerts", text: "Alerts marked \u201cflagged for review\u201d" },
      ],
    },
  ],
} as const;

export const safety = {
  id: "safety",
  heading: "Safety and privacy",
  intro:
    "What the product promises, and how it is built to keep the promise when the model behaves badly.",
  bullets: [
    "A keyword safety check the AI cannot lower",
    "If analysis fails, crisis resources are shown",
    "Every flag links to the exact quote",
    "No diagnosis, only what the patient said",
    "Consent you can revoke any time",
    "Audio is not stored",
  ],
  emergency:
    "Psylink is not an emergency service. If you are in danger, contact local emergency services or a crisis line now.",
  crisisLinkLabel: "See crisis resources",
} as const;

export const demoCta = {
  id: "demo",
  heading: "See it in two minutes.",
  intro: "Both demo accounts are seeded with synthetic data, so nothing here is a real person.",
  note: "All demo data is synthetic.",
} as const;

export const faq = {
  id: "faq",
  heading: "Questions people ask",
  items: [
    {
      question: "Does Psylink replace therapy?",
      answer:
        "No. It supports the care you already have by helping your visits start with a clearer picture.",
    },
    {
      question: "Who sees my data?",
      answer:
        "Only the psychologist or psychiatrist you link, and only while your consent is active. You can revoke it any time.",
    },
    {
      question: "What happens in a crisis?",
      answer:
        "Crisis resources are shown immediately and your provider is emailed a \u201cflagged for review\u201d alert. Alerts are not real-time and are not a substitute for emergency help.",
    },
    {
      question: "Is it clinically validated?",
      answer:
        "Not yet. Psylink is a hackathon prototype and the analysis can be wrong, which is why providers see the original transcript.",
    },
  ],
} as const;

export const footer = {
  links: [
    { label: "How it works", href: "#how" },
    { label: "Safety", href: "#safety" },
    { label: "FAQ", href: "#faq" },
    { label: "GitHub", href: product.githubUrl, external: true },
  ],
} as const;

/** Shared by the hero and the demo section, so the two can never drift apart. */
export const demoButtons = {
  patientLabel: "Try as patient",
  psychologistLabel: "Try as psychologist",
  /**
   * Shown while the demo starts. A cold free-tier backend really can take around a minute to answer
   * the first request, and a button that appears to do nothing reads as a broken product.
   */
  waitingLabel: "Waking up the demo, one moment...",
  errorNote: "The demo did not start. Please try again.",
  retryLabel: "Try again",
} as const;
