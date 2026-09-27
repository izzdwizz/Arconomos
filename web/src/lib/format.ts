/** Amounts arrive from the API as USDC's 6-decimal integer units, matching the on-chain
 * ERC-20 representation (see backend/app/db/models.py). */
export function formatUsdc(amountInBaseUnits: number): string {
  return (amountInBaseUnits / 1_000_000).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}
