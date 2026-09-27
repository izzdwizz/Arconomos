"use client";

import { createContext, useContext, type ReactNode } from "react";

export interface AuthValue {
  ready: boolean;
  authenticated: boolean;
  walletAddress: string | null;
  getAccessToken: () => Promise<string | null>;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthContextProvider({ value, children }: { value: AuthValue; children: ReactNode }) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthContextProvider");
  return ctx;
}

/** Used when NEXT_PUBLIC_PRIVY_APP_ID isn't set -- lets the app run locally without Privy
 * credentials configured yet, rather than crashing the whole render tree. */
export const unconfiguredAuth: AuthValue = {
  ready: true,
  authenticated: false,
  walletAddress: null,
  getAccessToken: async () => null,
  login: () => console.warn("NEXT_PUBLIC_PRIVY_APP_ID is not set -- sign-in is unavailable."),
  logout: () => {},
};
