"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";

/** Wraps our auth abstraction's access token fetch + our own POST /v1/session bootstrap
 * (creates the backend User row on first sign-in). Every other query depends on this
 * one's token. */
export function useSession() {
  const { ready, authenticated, getAccessToken, walletAddress, login, logout } = useAuth();

  const tokenQuery = useQuery({
    queryKey: ["access-token", walletAddress],
    queryFn: getAccessToken,
    enabled: ready && authenticated,
    staleTime: 5 * 60 * 1000,
  });

  const accessToken = tokenQuery.data ?? null;

  const sessionQuery = useQuery({
    queryKey: ["session", accessToken],
    queryFn: () => api.createSession(accessToken as string),
    enabled: Boolean(accessToken),
  });

  return {
    ready,
    authenticated,
    accessToken,
    user: sessionQuery.data,
    isLoading: !ready || (authenticated && (tokenQuery.isLoading || sessionQuery.isLoading)),
    login,
    logout,
  };
}
