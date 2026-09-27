const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, accessToken: string | null, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init?.body) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface VaultSummary {
  id: string;
  vault_addr: string;
  income_inbox: string;
  topup_inbox: string;
  payout_addr: string;
}

export interface DashboardSummary {
  vault_addr: string;
  balances: Record<string, number>;
  total: number;
  as_of_block: number;
}

export interface Decision {
  id: string;
  vault_id: string;
  trigger: string;
  reason: string;
  hash: string;
  prev_hash: string;
  tx_hash: string | null;
  policy_result: Record<string, unknown>;
  proposed: unknown[];
  created_at: string;
}

export const api = {
  createSession: (token: string) => request<{ id: string; wallet: string }>("/v1/session", token, { method: "POST" }),
  getMyVault: (token: string) => request<VaultSummary>("/v1/vaults/me", token),
  getDashboardSummary: (token: string) => request<DashboardSummary>("/v1/dashboard/summary", token),
  listDecisions: (token: string) => request<Decision[]>("/v1/decisions", token),
};
