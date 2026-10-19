import { createContext, ReactNode, useCallback, useContext, useLayoutEffect, useRef, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";

type FormState = { dirty: boolean; busy: boolean; discard: () => void };
type LeaveAction = () => void;
const UnsavedContext = createContext<{
  register: (key: symbol, state: FormState) => () => void;
  requestLeave: (action: LeaveAction) => void;
} | null>(null);

/** Only live form state is tracked. Business drafts never enter browser storage. */
export function UnsavedChangesProvider({ children }: { children: ReactNode }) {
  const forms = useRef(new Map<symbol, FormState>());
  const [pending, setPending] = useState<{ action: LeaveAction } | null>(null);
  const register = useCallback((key: symbol, state: FormState) => {
    forms.current.set(key, state);
    return () => { forms.current.delete(key); };
  }, []);
  const requestLeave = useCallback((action: LeaveAction) => {
    const states = [...forms.current.values()];
    if (states.some((state) => state.busy)) return;
    if (states.some((state) => state.dirty)) setPending({ action });
    else action();
  }, []);

  useLayoutEffect(() => {
    function preventUnload(event: BeforeUnloadEvent) {
      if (![...forms.current.values()].some((state) => state.dirty || state.busy)) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", preventUnload);
    return () => window.removeEventListener("beforeunload", preventUnload);
  }, []);

  return <UnsavedContext.Provider value={{ register, requestLeave }}>
    {children}
    <ConfirmDialog open={pending !== null} title="放弃未保存的农活？"
      description="已填写的内容尚未确认保存，离开会丢弃本次填写。若刚才网络中断，请先重试保存或核对台账。"
      confirmLabel="放弃并离开" busy={false}
      onCancel={() => setPending(null)}
      onConfirm={() => {
        const action = pending?.action;
        setPending(null);
        forms.current.forEach((state) => { if (state.dirty) state.discard(); });
        action?.();
      }} />
  </UnsavedContext.Provider>;
}

export function useRequestLeave() {
  const context = useContext(UnsavedContext);
  if (!context) throw new Error("Missing UnsavedChangesProvider");
  return context.requestLeave;
}

export function useUnsavedChanges(dirty: boolean, busy: boolean, onDiscard: () => void) {
  const context = useContext(UnsavedContext);
  const key = useRef(Symbol("ledger form"));
  const register = context?.register;
  const discard = useRef(onDiscard);
  discard.current = onDiscard;
  useLayoutEffect(() => register?.(key.current, { dirty, busy, discard: () => discard.current() }), [register, dirty, busy]);
}
