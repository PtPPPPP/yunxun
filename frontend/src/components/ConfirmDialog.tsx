import { useId, useRef } from "react";
import { useDialogFocus } from "../hooks/useDialogFocus";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  const { open, title, description, confirmLabel, busy, onConfirm, onCancel } = props;
  const dialog = useRef<HTMLElement>(null);
  const titleId = useId();
  useDialogFocus(dialog, open, () => { if (!busy) onCancel(); });

  if (!open) return null;

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={() => { if (!busy) onCancel(); }}>
      <section
        className="confirm-dialog"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h3 id={titleId}>{title}</h3>
        <p>{description}</p>
        <div className="inline-actions confirm-dialog__actions">
          <button className="ghost-button" type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="secondary-button danger-button" type="button" onClick={onConfirm} disabled={busy || props.confirmDisabled}>
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
