"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useSession } from "../hooks/useSession";

// Auth-gated: nothing here can be usefully prerendered at build time.
export const dynamic = "force-dynamic";

export default function LandingPage() {
  const { ready, authenticated, login } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (ready && authenticated) router.replace("/dashboard");
  }, [ready, authenticated, router]);

  return (
    <div className="container" style={{ paddingTop: 96, paddingBottom: 96 }}>
      <div style={{ maxWidth: 640, display: "flex", flexDirection: "column", gap: 20 }} className="fade-in">
        <span className="eyebrow">Oikonomos</span>
        <h1 style={{ fontSize: 44, lineHeight: 1.1 }}>
          Every deposit, split into tax, bills, goals, pay and savings — automatically.
        </h1>
        <p style={{ fontSize: 17, lineHeight: 1.6 }}>
          Fund a wallet, set your rules once, and an agent adjusts your splits as it forecasts
          what&rsquo;s coming. No crypto experience required.
        </p>
        <div>
          <button type="button" className="pill-button pill-button--accent" onClick={() => login()} disabled={!ready}>
            Sign in with email
          </button>
        </div>
      </div>
    </div>
  );
}
