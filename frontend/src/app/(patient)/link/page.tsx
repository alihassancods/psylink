import type { Metadata } from "next";

import { LinkForm } from "@/components/patient/link-form";

export const metadata: Metadata = { title: "Link your clinician · Psylink" };

export default function LinkPage() {
  return <LinkForm />;
}
