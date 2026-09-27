"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState, type ReactNode } from "react";

import { AuthContextProvider, unconfiguredAuth } from "./auth-context";
import { ThemeProvider } from "./theme";

const PrivyClientProvider = dynamic(
  () => import("./PrivyClientProvider").then((m) => m.PrivyClientProvider),
  { ssr: false },
);

const privyConfigured = Boolean(process.env.NEXT_PUBLIC_PRIVY_APP_ID);

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  const authWrapped = privyConfigured ? (
    <PrivyClientProvider>{children}</PrivyClientProvider>
  ) : (
    <AuthContextProvider value={unconfiguredAuth}>{children}</AuthContextProvider>
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>{authWrapped}</ThemeProvider>
    </QueryClientProvider>
  );
}
