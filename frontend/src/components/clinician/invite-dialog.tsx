"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { CopyIcon } from "lucide-react";

import { ApiError, api } from "@/lib/api";
import type { InviteCreated } from "@/types/api";

/**
 * Clinician-side linking. The plaintext code exists only in the create response, so it is shown
 * here once, with a copy button, and is never expected to be retrievable later.
 */
export function InviteDialog() {
  const [invite, setInvite] = useState<InviteCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);

  async function create() {
    setPending(true);
    setError(null);
    setCopied(false);
    try {
      setInvite(await api.createInvite());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "We could not create a code.");
    } finally {
      setPending(false);
    }
  }

  async function copy() {
    if (!invite) return;
    try {
      await navigator.clipboard.writeText(invite.code);
      setCopied(true);
    } catch {
      setCopied(false);
      setError("Your browser blocked copying. Select the code and copy it manually.");
    }
  }

  const expires = invite ? new Date(invite.expires_at) : null;

  return (
    <Dialog
      onOpenChange={(open) => {
        if (open) {
          setInvite(null);
          setError(null);
          setCopied(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">New invite code</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a patient</DialogTitle>
          <DialogDescription>
            The code works once and expires within a day. Send it through a channel you already use
            with the patient.
          </DialogDescription>
        </DialogHeader>

        {!invite && !error ? (
          <Button size="lg" onClick={() => void create()} disabled={pending}>
            {pending ? "Creating…" : "Create a code"}
          </Button>
        ) : null}

        {invite ? (
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">
              This code is shown once. It cannot be retrieved later.
            </p>
            <div className="flex items-center gap-2">
              <output
                className="flex-1 rounded-lg border border-border bg-muted px-3 py-2 font-mono text-lg tracking-widest"
                aria-label="Invite code"
              >
                {invite.code}
              </output>
              <Button variant="outline" size="icon" onClick={() => void copy()} aria-label="Copy invite code">
                <CopyIcon className="size-4" aria-hidden />
              </Button>
            </div>
            {copied ? (
              <p role="status" className="text-sm text-risk-low">
                Copied.
              </p>
            ) : null}
            {expires && !Number.isNaN(expires.getTime()) ? (
              <p className="text-sm text-muted-foreground">
                Expires {expires.toLocaleString(undefined, {
                  day: "numeric",
                  month: "short",
                  hour: "numeric",
                  minute: "2-digit",
                })}
                .
              </p>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
