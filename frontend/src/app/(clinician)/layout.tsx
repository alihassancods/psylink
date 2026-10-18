import { ClinicianShell } from "@/components/clinician/clinician-shell";
import { RequireRole } from "@/lib/auth/require-role";

export default function ClinicianLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="clinician">
      <ClinicianShell>{children}</ClinicianShell>
    </RequireRole>
  );
}
