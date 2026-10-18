/**
 * Crisis content, editable and deliberately region-neutral: the backend only says
 * `show_crisis_resources`, so the numbers and wording are ours to maintain. Nothing here claims a
 * specific country's line; the instruction to reach local emergency services is stated outright.
 */

export interface CrisisResource {
  label: string;
  detail: string;
  href?: string;
}

export const CRISIS_RESOURCES: {
  headline: string;
  intro: string;
  steps: string[];
  resources: CrisisResource[];
  closing: string;
} = {
  headline: "If you need help right now",
  intro:
    "Psylink is not emergency care and cannot call for help. If you feel unsafe, or you might hurt yourself, please reach a person or a service that can respond immediately.",
  steps: [
    "If you are in immediate danger, contact your local emergency services.",
    "If you can, tell someone nearby what is going on.",
    "If you have a crisis or support line in your country, you can call or text it now.",
  ],
  resources: [
    {
      label: "Local emergency services",
      detail:
        "The emergency number differs by country — in much of Europe it is 112, in the United States 911, in the United Kingdom 999. Use the number for where you are.",
    },
    {
      label: "A national crisis or support line",
      detail:
        "Many countries run a free line you can call or text at any hour. Add your local line here to make this screen specific to your region.",
    },
    {
      label: "Your care team",
      detail:
        "If your psychologist or psychiatrist gave you an out-of-hours contact, it is worth using it for what you have just told us.",
    },
  ],
  closing:
    "You can also save this screen, or show it to someone with you. What you wrote in Psylink stays in Psylink — it is not sent to emergency services.",
};
