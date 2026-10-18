import type { Metadata } from "next";

import { AlertsView } from "@/components/clinician/alerts-view";

export const metadata: Metadata = { title: "Alerts · Psylink" };

export default function AlertsPage() {
  return <AlertsView />;
}
