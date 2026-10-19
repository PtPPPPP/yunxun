import { useCallback, useRef } from "react";

/** Async callbacks retain the account that started them, even after logout. */
export function useAccountGuard(accountId: string | null) {
  const current = useRef(accountId);
  current.current = accountId;
  return useCallback(() => accountId !== null && current.current === accountId, [accountId]);
}
