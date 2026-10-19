import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

const SessionContext = createContext<{
  epoch: number;
  advance: () => number;
  capture: () => number;
  isCurrent: (epoch: number) => boolean;
} | null>(null);

/** 账号 ID 不足以区分退出后再次登录同一账号；轮次在边界操作开始时同步失效。 */
export function SessionBoundary({ children }: { children: ReactNode }) {
  const current = useRef(0);
  const [epoch, setEpoch] = useState(0);
  const advance = useCallback(() => {
    const next = ++current.current;
    setEpoch(next);
    return next;
  }, []);
  const capture = useCallback(() => current.current, []);
  const isCurrent = useCallback((ticket: number) => current.current === ticket, []);
  const value = useMemo(() => ({ epoch, advance, capture, isCurrent }), [epoch, advance, capture, isCurrent]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessionBoundary() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("缺少 SessionBoundary");
  return session;
}

export function useSessionGuard() {
  const { epoch, isCurrent } = useSessionBoundary();
  return useCallback(() => isCurrent(epoch), [epoch, isCurrent]);
}
