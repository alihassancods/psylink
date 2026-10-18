import type { Metadata } from "next";

import { ConsentView } from "@/components/patient/consent-view";

export const metadata: Metadata = { title: "Before you start · Psylink" };

export default function ConsentPage() {
  return <ConsentView />;
}
