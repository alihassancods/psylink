"use client";

import { useState } from "react";
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
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useApi } from "@/lib/use-api";
import type { CheckinSummary } from "@/types/api";

const PAGE_SIZE = 100;

/**
 * Patient history. Newest first, as the API returns them. Deleting is confirmed, and deleting the
 * newest item while a re-record is in flight is simply a 404 — treated as "already gone".
 *
 * Mood is not shown because `GET /api/checkins` does not return a mood score, and raw risk labels
 * are kept off patient screens on purpose.
 */
export function HistoryView() {
  const [nonce, setNonce] = useState(0);
  const checkins = useApi(
    () => api.listCheckins({ limit: PAGE_SIZE, offset: 0 }),
    `history-${nonce}`,
  );
  const [pendingDelete, setPendingDelete] = useState<CheckinSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const items = checkins.data?.items ?? [];

  async function confirmDelete() {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteCheckin(pendingDelete.checkin_id);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        setDeleteError(
          error instanceof ApiError ? error.message : "We could not delete that check-in.",
        );
        setDeleting(false);
        return;
      }
    }
    setPendingDelete(null);
    setDeleting(false);
    setNonce((value) => value + 1);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-lg font-semibold">Your check-ins</h1>
        <Link
          className="inline-flex min-h-11 items-center text-sm text-primary underline underline-offset-4"
          href="/checkin"
        >
          New check-in
        </Link>
      </div>

      {checkins.status === "loading" ? <CardListSkeleton count={4} /> : null}

      {checkins.status === "error" ? (
        <ErrorPanel
          title="We could not load your check-ins"
          message={checkins.message}
          onRetry={() => void checkins.reload()}
        />
      ) : null}

      {checkins.status === "success" && items.length === 0 ? (
        <EmptyState
          title="No check-ins yet"
          description="When you record or write a check-in it appears here, newest first."
          action={
            <Button asChild>
              <Link href="/checkin">Start your first check-in</Link>
            </Button>
          }
        />
      ) : null}

      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.checkin_id}>
              <Card>
                <CardHeader className="pb-1">
                  <CardTitle className="text-sm font-medium">
                    {formatDateTime(item.created_at)}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {item.summary ??
                      (item.status === "analysis_failed"
                        ? "We could not summarise this one. It still shows as you wrote it."
                        : "No summary for this one.")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {item.transcript ? "Spoken and approved by you" : "Typed by you"}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setPendingDelete(item);
                        setDeleteError(null);
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}

      {items.length === PAGE_SIZE ? (
        <p className="text-xs text-muted-foreground">
          Showing your {PAGE_SIZE} most recent check-ins.
        </p>
      ) : null}

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this check-in?</DialogTitle>
            <DialogDescription>
              It is removed for you and for your care team. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          {pendingDelete ? (
            <p className="text-sm text-muted-foreground">{formatDateTime(pendingDelete.created_at)}</p>
          ) : null}
          {deleteError ? (
            <p role="alert" className="text-sm text-destructive">
              {deleteError}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Keep it
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete check-in"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
