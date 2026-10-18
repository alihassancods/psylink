import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 p-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Psylink</h1>
        <p className="text-muted-foreground">Your voice, between sessions.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Get started</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
            href="/login"
          >
            Log in
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-lg px-4 py-2 text-primary underline underline-offset-4"
            href="/signup"
          >
            Create an account
          </Link>
        </CardContent>
      </Card>
      <p className="text-sm text-muted-foreground">
        Psylink is not emergency care.
      </p>
    </main>
  );
}
