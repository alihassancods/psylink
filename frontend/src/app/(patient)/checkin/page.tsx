import type { Metadata } from "next";

import { CheckinFlow } from "@/components/checkin/checkin-flow";

export const metadata: Metadata = { title: "Check-in · Psylink" };

export default function CheckinPage() {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Nothing is saved until you submit, and you can stop at any point.
      </p>
      <CheckinFlow />
    </div>
  );
}
