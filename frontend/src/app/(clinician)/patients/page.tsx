import type { Metadata } from "next";

import { PatientList } from "@/components/clinician/patient-list";

export const metadata: Metadata = { title: "Patients · Psylink" };

export default function PatientsPage() {
  return <PatientList />;
}
