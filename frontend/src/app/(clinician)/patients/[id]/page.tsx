import { Suspense } from "react";
import type { Metadata } from "next";

import { PatientDetail } from "@/components/clinician/patient-detail";
import { PageLoading } from "@/components/states";

export const metadata: Metadata = { title: "Patient · Psylink" };

/**
 * `params` stays a promise (Next 16) and is unwrapped with `use` inside the client view, so this
 * segment can prerender without reading route data at the top level.
 */
export default function PatientPage(props: PageProps<"/patients/[id]">) {
  return (
    <Suspense fallback={<PageLoading />}>
      <PatientDetail params={props.params} />
    </Suspense>
  );
}
