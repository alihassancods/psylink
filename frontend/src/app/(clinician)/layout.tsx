import { ClinicianShell } from "@/components/clinician/clinician-shell";
import { RequireRole } from "@/lib/auth/require-role";

/** Same shape as the patient group: chrome first, guard around the page content only. */
export default function ClinicianLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClinicianShell>
      <RequireRole role="clinician">{children}</RequireRole>
    </ClinicianShell>
  );
}
