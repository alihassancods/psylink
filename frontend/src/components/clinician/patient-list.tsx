"use client";

import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { InviteDialog } from "@/components/clinician/invite-dialog";
import { RiskBadge } from "@/components/clinician/risk-badge";
import { formatRelativeDay } from "@/lib/utils";
import { asState, usePatientsQuery } from "@/lib/queries";

/**
 * Roster of currently consented patients, in the order the API returns them — open alerts first,
 * then most recent check-in. The list is a `ul` rather than a table because at 360px a five-column
 * table is unreadable, and each row already reads as one card.
 *
 * The roster carries `last_risk` and `last_summary` but no mood score, so the summary line stands
 * in for mood here; mood trends appear on the patient's own screen.
 */
export function PatientList() {
  const patients = asState(usePatientsQuery());
  const items = patients.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Patients</h1>
        <InviteDialog />
      </div>

      {patients.status === "loading" ? <CardListSkeleton count={3} /> : null}

      {patients.status === "error" ? (
        <ErrorPanel
          title="We could not load your patients"
          message={patients.message}
          onRetry={() => void patients.reload()}
        />
      ) : null}

      {patients.status === "success" && items.length === 0 ? (
        <EmptyState
          title="No patients yet"
          description="Nobody has linked to you with an invite code. Once a patient redeems one, their check-ins appear here."
        />
      ) : null}

      {items.length > 0 ? (
        <>
          <p className="text-sm text-muted-foreground">
            {items.length} patient{items.length === 1 ? "" : "s"} you can currently see. Sorted with
            open alerts first.
          </p>
          <ul className="space-y-3">
            {items.map((patient) => (
              <li key={patient.patient_id}>
                <Card className="transition-colors hover:bg-muted/60">
                  <CardHeader className="pb-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle>
                        <Link
                          className="inline-flex min-h-11 items-center text-base font-semibold underline-offset-4 hover:underline"
                          href={`/patients/${patient.patient_id}`}
                        >
                          {patient.display_name ?? "Patient"}
                        </Link>
                      </CardTitle>
                      <RiskBadge risk={patient.last_risk} />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Last check-in {formatRelativeDay(patient.last_checkin_at)}
                      {patient.open_alerts > 0 ? (
                        <span className="ml-2 font-medium text-risk-high">
                          {patient.open_alerts} open alert{patient.open_alerts === 1 ? "" : "s"}
                        </span>
                      ) : null}
                    </p>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground">
                      {patient.last_summary ?? "No check-ins shared yet."}
                    </p>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
