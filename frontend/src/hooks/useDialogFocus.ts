import { RefObject, useEffect, useRef } from "react";

let openDialogs = 0;
let previousOverflow = "";

export function useDialogFocus(ref: RefObject<HTMLElement>, open: boolean, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    if (openDialogs++ === 0) previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.focus();
    const focusables = () => [...dialog.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex='0']")]
      .filter((element) => !element.matches(":disabled") && element.getClientRects().length > 0);
    function keydown(event: KeyboardEvent) {
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs[dialogs.length - 1] !== dialog) return;
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const items = focusables();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) {
        event.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      if (--openDialogs === 0) document.body.style.overflow = previousOverflow;
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [ref, open]);
}
