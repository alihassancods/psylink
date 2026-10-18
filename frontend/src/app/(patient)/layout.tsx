import { PatientShell } from "@/components/patient/patient-shell";
import { RequireRole } from "@/lib/auth/require-role";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="patient" requireConsent>
      <PatientShell>{children}</PatientShell>
    </RequireRole>
  );
}
