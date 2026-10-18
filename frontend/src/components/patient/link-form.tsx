"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import { PATIENT_LANDING } from "@/lib/auth/session-provider";
import { queryKeys } from "@/lib/query-keys";

/**
 * Invite-code linking. The backend treats a redeemed code as consent being granted, so this form
 * is the moment sharing actually starts. Codes tolerate capitals, spaces and dashes.
 */
export function LinkForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await api.redeemInvite(code);
      // The guard reads this same cache key. Without this it keeps its pre-link answer — "not
      // linked" — and throws a person who just linked straight back at /consent.
      await queryClient.invalidateQueries({ queryKey: queryKeys.consent });
      router.replace(PATIENT_LANDING);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "We could not use that code. Check it and try again.",
      );
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Enter your invite code</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="pb-4 text-sm text-muted-foreground">
          Your psychologist or psychiatrist gives you this code. It works once and expires the next
          day. Linking is what lets them read the check-ins you submit from now on.
        </p>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-code">Invite code</Label>
            <Input
              id="invite-code"
              name="invite-code"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              inputMode="text"
              placeholder="a1b2c3d4e5"
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
              aria-describedby={error ? "link-error" : "link-help"}
              aria-invalid={error ? true : undefined}
              className="font-mono tracking-wide"
            />
            <p id="link-help" className="text-xs text-muted-foreground">
              Letters and numbers, 10 characters. Capitals, spaces and dashes are fine.
            </p>
          </div>

          {error ? (
            <p id="link-error" role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button type="submit" size="lg" className="w-full" disabled={pending || code.trim().length < 4}>
            {pending ? "Linking…" : "Start sharing"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
