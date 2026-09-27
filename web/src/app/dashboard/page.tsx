"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useSession } from "../../hooks/useSession";
import { api } from "../../lib/api";
import { formatUsdc } from "../../lib/format";

// Auth-gated: nothing here can be usefully prerendered at build time.
export const dynamic = "force-dynamic";

const BUCKET_LABELS: Record<string, string> = {
  Tax: "Tax",
  Bills: "Bills",
  Goals: "Goals",
  OwnerPay: "Owner pay",
  Buffer: "Buffer",
  Savings: "Savings",
};

export default function DashboardPage() {
  const { ready, authenticated, accessToken } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (ready && !authenticated) router.replace("/");
  }, [ready, authenticated, router]);

  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary", accessToken],
    queryFn: () => api.getDashboardSummary(accessToken as string),
    enabled: Boolean(accessToken),
  });

  const decisionsQuery = useQuery({
    queryKey: ["decisions", accessToken],
    queryFn: () => api.listDecisions(accessToken as string),
    enabled: Boolean(accessToken),
  });

  if (!ready || !authenticated) return null;

  return (
    <div className="container" style={{ paddingTop: 48, paddingBottom: 64, display: "flex", flexDirection: "column", gap: 40 }}>
      <div>
        <span className="eyebrow">Balances</span>
        <h1 style={{ fontSize: 28, marginTop: 8 }}>Your buckets</h1>
      </div>

      {summaryQuery.isLoading && <p>Loading balances…</p>}
      {summaryQuery.isError && <p style={{ color: "var(--bad)" }}>Couldn&rsquo;t load balances.</p>}
      {summaryQuery.data && (
        <div className="card-grid">
          {Object.entries(summaryQuery.data.balances).map(([bucket, amount]) => (
            <div className="card" key={bucket}>
              <span className="card__label">{BUCKET_LABELS[bucket] ?? bucket}</span>
              <span className="card__value">{formatUsdc(amount)}</span>
            </div>
          ))}
        </div>
      )}

      <div>
        <span className="eyebrow">Agent log</span>
        <h2 style={{ fontSize: 22, marginTop: 8, marginBottom: 16 }}>Recent decisions</h2>
        <div className="card">
          {decisionsQuery.isLoading && <p>Loading decisions…</p>}
          {decisionsQuery.data?.length === 0 && <p>No decisions yet — they&rsquo;ll show up here as they happen.</p>}
          {decisionsQuery.data?.map((decision) => (
            <div className="log-entry" key={decision.id}>
              <div className="log-entry__meta">
                <span className="badge">{decision.trigger}</span>
                <span>{new Date(decision.created_at).toLocaleString()}</span>
              </div>
              <span className="log-entry__reason">{decision.reason}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
