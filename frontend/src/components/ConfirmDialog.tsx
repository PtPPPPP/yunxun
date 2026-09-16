interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  const { open, title, description, confirmLabel, busy, onConfirm, onCancel } = props;

  if (!open) return null;

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h3>{title}</h3>
        <p>{description}</p>
        <div className="inline-actions confirm-dialog__actions">
          <button className="ghost-button" type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="secondary-button danger-button" type="button" onClick={onConfirm} disabled={busy}>
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
