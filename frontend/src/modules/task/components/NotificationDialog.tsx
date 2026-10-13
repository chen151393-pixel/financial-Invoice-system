import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "../../../shared/components/Button";

export function NotificationDialog({
  title,
  onClose,
  children,
  busy = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="itn-dialog"
      aria-labelledby="itn-dialog-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <header>
        <h3 id="itn-dialog-title">{title}</h3>
        <Button disabled={busy} onClick={onClose}>
          关闭
        </Button>
      </header>
      {children}
    </dialog>
  );
}
