import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "../Button";

/** 模态弹窗：打开后焦点进入弹窗、背景不可操作，关闭后焦点回到触发控件；提交期间（busy）不能关闭。 */
export function Dialog({
  title,
  onClose,
  children,
  busy = false,
  className = "",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
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
      className={`ui-dialog ${className}`.trim()}
      aria-labelledby={titleId}
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <header className="ui-dialog__header">
        <h3 id={titleId}>{title}</h3>
        <Button disabled={busy} onClick={onClose}>
          关闭
        </Button>
      </header>
      {children}
    </dialog>
  );
}
