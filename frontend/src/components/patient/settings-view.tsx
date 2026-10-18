"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorPanel, CardListSkeleton } from "@/components/states";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/auth/session-provider";
import { queryKeys } from "@/lib/query-keys";
import { asState, useCheckinsQuery, useConsentQuery } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

/**
 * Privacy and sharing. Revoking is real (`DELETE /api/consent/{clinician_id}`, which closes the
 * history to that clinician, not just future rows) and deleting check-ins is real.
 *
 * Disabled rather than faked: there is no endpoint to delete the account or the Supabase identity,
 * so that control says so instead of pretending to work.
 */
export function SettingsView() {
  const queryClient = useQueryClient();
  // Same cached query the route guard uses, so the two can never disagree about who is linked.
  const consentQuery = useConsentQuery(true);
  const consent = asState(consentQuery);
  const links = consent.data ?? [];
  const { signOut } = useSession();
  const checkins = asState(useCheckinsQuery(100));

  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [deleteAllBusy, setDeleteAllBusy] = useState(false);
  const [deletedCount, setDeletedCount] = useState<number | null>(null);

  async function revoke(clinicianId: string) {
    setRevokeBusy(true);
    setError(null);
    try {
      await api.revokeConsent(clinicianId);
      setRevokeTarget(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not stop that share.");
      setRevokeTarget(null);
    } finally {
      setRevokeBusy(false);
    }
    // The guard reads this same key: refreshing it is what bounces an unlinked patient to /consent
    // without a page reload.
    await queryClient.invalidateQueries({ queryKey: queryKeys.consent });
    await queryClient.invalidateQueries({ queryKey: queryKeys.patients });
  }

  async function deleteEverything() {
    const items = checkins.data?.items ?? [];
    setDeleteAllBusy(true);
    setError(null);
    let done = 0;
    for (const item of items) {
      try {
        await api.deleteCheckin(item.checkin_id);
        done += 1;
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          done += 1;
          continue;
        }
        setError("We could not finish deleting everything. Some check-ins are still there.");
        break;
      }
    }
    setDeletedCount(done);
    setDeleteAllBusy(false);
    setDeleteAllOpen(false);
    // Their detail records are immutable-cached; drop them too or a clinician could still read one.
    queryClient.removeQueries({ queryKey: ["checkin"] });
    await queryClient.invalidateQueries({ queryKey: ["checkins"] });
    await queryClient.invalidateQueries({ queryKey: queryKeys.patients });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Privacy and sharing</h1>

      <Card>
        <CardHeader>
          <CardTitle>Who can read your check-ins</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {consent.status === "loading" ? <CardListSkeleton count={1} /> : null}
          {consent.status === "error" ? (
            <ErrorPanel
              title="We could not load your sharing settings"
              message={consent.message}
              onRetry={() => void consent.reload()}
            />
          ) : null}
          {consent.status === "success" && links.length === 0 ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Nobody is linked right now, so your check-ins are only stored for you.
              </p>
              <Button asChild>
                <Link href="/link">Link your psychologist or psychiatrist</Link>
              </Button>
            </div>
          ) : null}
          {links.map((link) => (
            <div
              key={link.consent_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-3"
            >
              <div>
                <p className="text-sm font-medium">
                  {link.clinician_name ?? "A clinician on your care team"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Sharing since {formatDateTime(link.granted_at)}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setRevokeTarget(link.clinician_id);
                  setError(null);
                }}
              >
                Stop sharing
              </Button>
            </div>
          ))}
          {links.length > 0 ? (
            <p className="text-xs text-muted-foreground">
              Stopping sharing also hides the check-ins you sent before. You can link again later
              with a new invite code.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your data</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Audio is never stored: it is turned into text, you approve the text, and only the text
            is kept. You can delete any check-in from your history, or all of them here.
          </p>

          {deletedCount !== null ? (
            <p role="status" className="text-risk-low">
              {deletedCount === 0
                ? "Nothing was deleted."
                : `${deletedCount} check-in${deletedCount === 1 ? "" : "s"} deleted.`}
            </p>
          ) : null}

          {error ? (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row">
            <Button
              variant="outline"
              onClick={() => setDeleteAllOpen(true)}
              disabled={(checkins.data?.items.length ?? 0) === 0}
            >
              Delete all my check-ins
            </Button>
            <Button variant="ghost" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>

          <div className="rounded-lg border border-border bg-muted p-3 text-xs text-muted-foreground">
            <p className="font-medium text-foreground">Deleting your account</p>
            <p>
              Psylink cannot delete your sign-in yet — that lives with the account provider and is
              not something this app can do for you. Ask your care service to remove the account and
              its data.
            </p>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stop sharing with this clinician?</DialogTitle>
            <DialogDescription>
              They will lose access to everything you sent, including earlier check-ins.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>
              Keep sharing
            </Button>
            <Button
              variant="destructive"
              disabled={revokeBusy}
              onClick={() => revokeTarget ? void revoke(revokeTarget) : undefined}
            >
              {revokeBusy ? "Stopping…" : "Stop sharing"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteAllOpen} onOpenChange={(open) => !open && setDeleteAllOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete every check-in?</DialogTitle>
            <DialogDescription>
              {`${checkins.data?.items.length ?? 0} check-ins and their summaries will be removed. This cannot be undone.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteAllOpen(false)}>
              Keep them
            </Button>
            <Button
              variant="destructive"
              disabled={deleteAllBusy}
              onClick={() => void deleteEverything()}
            >
              {deleteAllBusy ? "Deleting…" : "Delete all"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
