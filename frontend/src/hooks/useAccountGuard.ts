import { useCallback, useRef } from "react";
import { useSessionGuard } from "./useSessionBoundary";

/** Async callbacks retain the account that started them, even after logout. */
export function useAccountGuard(accountId: string | null) {
  const current = useRef(accountId);
  current.current = accountId;
  const sessionCurrent = useSessionGuard();
  return useCallback(() => sessionCurrent() && accountId !== null && current.current === accountId, [accountId, sessionCurrent]);
}
