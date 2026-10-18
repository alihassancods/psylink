import { Suspense } from "react";
import type { Metadata } from "next";

import { CheckinDetail } from "@/components/clinician/checkin-detail";
import { PageLoading } from "@/components/states";

export const metadata: Metadata = { title: "Check-in · Psylink" };

/**
 * Nested under the patient because the detail endpoint needs both ids — `GET
 * /api/patients/{patientId}/checkins/{checkinId}`. The spec's flat `/checkins/[id]` would need a
 * single-id route the backend does not serve.
 */
export default function CheckinPage(props: PageProps<"/patients/[id]/checkins/[checkinId]">) {
  return (
    <Suspense fallback={<PageLoading />}>
      <CheckinDetail params={props.params} />
    </Suspense>
  );
}
