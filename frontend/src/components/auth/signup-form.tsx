"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/auth/session-provider";

/**
 * Self-service signup creates patient accounts only. The database's insert policy allows a
 * caller to write their own profile just as a patient, so a clinician account is provisioned by
 * the service role — this screen says so instead of letting someone build a fake one.
 */
export function SignupForm() {
  const router = useRouter();
  const { signUpPatient } = useSession();
  const [role, setRole] = useState<"patient" | "clinician">("patient");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setDone(null);
    try {
      const { needsEmailConfirmation } = await signUpPatient({
        email,
        password,
        displayName: displayName.trim(),
      });
      if (needsEmailConfirmation) {
        setDone("We sent a confirmation link. Confirm your email, then log in.");
        setPending(false);
        return;
      }
      router.replace("/consent");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "We could not create your account.");
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create an account</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Who is using Psylink?</legend>
            <div className="space-y-2">
              <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-muted">
                <input
                  type="radio"
                  name="role"
                  value="patient"
                  checked={role === "patient"}
                  onChange={() => setRole("patient")}
                  className="mt-1 size-4 accent-[var(--primary)]"
                />
                <span>
                  <span className="block text-sm font-medium">I am a patient</span>
                  <span className="block text-xs text-muted-foreground">
                    Record check-ins and share them with your psychologist or psychiatrist.
                  </span>
                </span>
              </label>
              <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border p-3 hover:bg-muted">
                <input
                  type="radio"
                  name="role"
                  value="clinician"
                  checked={role === "clinician"}
                  onChange={() => setRole("clinician")}
                  className="mt-1 size-4 accent-[var(--primary)]"
                />
                <span>
                  <span className="block text-sm font-medium">
                    I am a psychologist or psychiatrist
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    Review the check-ins your patients choose to share.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>

          {role === "clinician" ? (
            <div className="space-y-2 rounded-lg border border-border bg-muted p-3 text-sm text-muted-foreground">
              <p>
                Clinician accounts are created by the service that runs your clinic, so they cannot
                be signed up here. Ask your administrator to set yours up, or use{" "}
                <Link className="text-primary underline underline-offset-4" href="/login">
                  log in
                </Link>{" "}
                with the account you already have.
              </p>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="display-name">Name they will see</Label>
                <Input
                  id="display-name"
                  name="display-name"
                  autoComplete="name"
                  required
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  aria-describedby={error ? "signup-error" : undefined}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  aria-describedby={error ? "signup-error" : undefined}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-describedby={error ? "signup-error" : "password-help"}
                />
                <p id="password-help" className="text-xs text-muted-foreground">
                  At least 8 characters.
                </p>
              </div>

              {error ? (
                <p id="signup-error" role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              ) : null}
              {done ? (
                <p role="status" className="text-sm text-risk-low">
                  {done}
                </p>
              ) : null}

              <Button type="submit" className="w-full" size="lg" disabled={pending}>
                {pending ? "Creating account…" : "Create account"}
              </Button>
            </>
          )}
        </form>

        <div className="mt-4 flex justify-center">
          <Link
            className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
            href="/login"
          >
            I already have an account
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
