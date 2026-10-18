import Link from "next/link";

import { EmptyState } from "@/components/states";

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-md p-6">
      <EmptyState
        title="We could not find that page"
        description="The link may be out of date, or the item may no longer be there."
        action={
          <ButtonLink />
        }
      />
    </main>
  );
}

function ButtonLink() {
  return (
    <Link
      className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
      href="/"
    >
      Back to Psylink
    </Link>
  );
}
