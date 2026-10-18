import { PatientShell } from "@/components/patient/patient-shell";
import { RequireRole } from "@/lib/auth/require-role";

/**
 * The shell renders first and the guard wraps only the page content, so the header, the "Need help
 * now?" control and the not-emergency-care footer are in the prerendered static shell instead of
 * appearing only after the session check resolves.
 */
export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <PatientShell>
      <RequireRole role="patient" requireConsent>
        {children}
      </RequireRole>
    </PatientShell>
  );
}
