"use client";

import { useState } from "react";
import Link from "next/link";

import { RiskBadge } from "@/components/clinician/risk-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardListSkeleton, EmptyState, ErrorPanel } from "@/components/states";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useApi } from "@/lib/use-api";
import type { Alert } from "@/types/api";

const FILTERS = ["open", "all"] as const;
type Filter = (typeof FILTERS)[number];

/**
 * Alert queue. Acknowledging is not idempotent on this backend — a second call is a 404 — so the
 * button disables while a request is in flight and a 404 is treated as "someone already did it".
 */
export function AlertsView() {
  const [filter, setFilter] = useState<Filter>("open");
  const [nonce, setNonce] = useState(0);
  const alerts = useApi(() => api.listAlerts(filter, 50), `alerts-${filter}-${nonce}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const items = alerts.data ?? [];

  async function acknowledge(alert: Alert) {
    if (busy) return;
    setBusy(alert.alert_id);
    setError(null);
    try {
      await api.acknowledgeAlert(alert.alert_id);
    } catch (caught) {
      if (!(caught instanceof ApiError && caught.status === 404)) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "We could not acknowledge that alert.",
        );
      }
      // A 404 means it was already acknowledged, or the patient withdrew consent. Either way the
      // list is stale, so it is refetched below rather than left showing a dead button.
    } finally {
      setBusy(null);
    }
    setNonce((value) => value + 1);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Alerts</h1>
        <div className="flex items-center gap-1" role="group" aria-label="Alert filter">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={filter === option}
              onClick={() => setFilter(option)}
              className={
                filter === option
                  ? "min-h-11 rounded-lg border border-primary bg-primary/10 px-3 text-sm font-medium text-primary"
                  : "min-h-11 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground hover:bg-muted"
              }
            >
              {option === "open" ? "Needs review" : "All"}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {alerts.status === "loading" ? <CardListSkeleton count={3} /> : null}

      {alerts.status === "error" ? (
        <ErrorPanel
          title="We could not load alerts"
          message={alerts.message}
          onRetry={() => void alerts.reload()}
        />
      ) : null}

      {alerts.status === "success" && items.length === 0 ? (
        <EmptyState
          title={filter === "open" ? "Nothing needs review" : "No alerts yet"}
          description={
            filter === "open"
              ? "An alert appears when a check-in comes back high risk. Acknowledging one here does not change its risk level."
              : "Alerts are raised for high-risk check-ins only."
          }
        />
      ) : null}

      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((alert) => (
            <li key={alert.alert_id}>
              <Card>
                <CardHeader className="pb-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-sm font-medium">
                      <Link
                        className="inline-flex min-h-11 items-center underline-offset-4 hover:underline"
                        href={`/patients/${alert.patient_id}`}
                      >
                        {alert.patient_name ?? "Patient"}
                      </Link>
                    </CardTitle>
                    <RiskBadge risk={alert.severity} />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(alert.created_at)}
                    {alert.acknowledged_at
                      ? ` · acknowledged ${formatDateTime(alert.acknowledged_at)}`
                      : ""}
                  </p>
                </CardHeader>
                <CardContent className="flex flex-wrap items-end justify-between gap-3">
                  <p className="text-sm text-muted-foreground">{alert.message}</p>
                  {alert.acknowledged_at ? (
                    <p className="text-xs text-muted-foreground">Acknowledged</p>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => void acknowledge(alert)}
                      disabled={busy === alert.alert_id}
                    >
                      {busy === alert.alert_id ? "Acknowledging…" : "Acknowledge"}
                    </Button>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}

      {items.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          Alerts do not carry the check-in that raised them, so open the patient and start with their
          most recent record.
        </p>
      ) : null}
    </div>
  );
}
