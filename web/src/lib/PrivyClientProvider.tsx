"use client";

import { PrivyProvider, usePrivy } from "@privy-io/react-auth";
import type { ReactNode } from "react";

import { AuthContextProvider, type AuthValue } from "./auth-context";

/** Split out so it can be loaded via next/dynamic with ssr:false in providers.tsx --
 * PrivyProvider errors if it's ever rendered during Next's server-side render pass. */
export function PrivyClientProvider({ children }: { children: ReactNode }) {
  const privyAppId = process.env.NEXT_PUBLIC_PRIVY_APP_ID ?? "";

  return (
    <PrivyProvider
      appId={privyAppId}
      config={{
        loginMethods: ["email", "sms"],
        appearance: { theme: "light", accentColor: "#5b4cf5" },
        embeddedWallets: { ethereum: { createOnLogin: "users-without-wallets" } },
      }}
    >
      <PrivyAuthBridge>{children}</PrivyAuthBridge>
    </PrivyProvider>
  );
}

function PrivyAuthBridge({ children }: { children: ReactNode }) {
  const { ready, authenticated, user, getAccessToken, login, logout } = usePrivy();

  const value: AuthValue = {
    ready,
    authenticated,
    walletAddress: user?.wallet?.address ?? null,
    getAccessToken,
    login: () => login(),
    logout: () => void logout(),
  };

  return <AuthContextProvider value={value}>{children}</AuthContextProvider>;
}
