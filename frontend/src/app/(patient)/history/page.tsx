import type { Metadata } from "next";

import { HistoryView } from "@/components/patient/history-view";

export const metadata: Metadata = { title: "Your history · Psylink" };

export default function HistoryPage() {
  return <HistoryView />;
}
