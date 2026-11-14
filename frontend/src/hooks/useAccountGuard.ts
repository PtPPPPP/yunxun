import { useCallback, useRef } from "react";
import { useSessionGuard } from "./useSessionBoundary";

/** 异步回调始终绑定发起时的账号，退出后迟到的响应不会落到新会话。 */
export function useAccountGuard(accountId: string | null) {
  const current = useRef(accountId);
  current.current = accountId;
  const sessionCurrent = useSessionGuard();
  return useCallback(() => sessionCurrent() && accountId !== null && current.current === accountId, [accountId, sessionCurrent]);
}
