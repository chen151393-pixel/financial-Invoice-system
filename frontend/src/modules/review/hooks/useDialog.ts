import { useEffect, useRef } from "react";

/** 打开即以模态方式显示原生对话框；关闭后焦点回到打开前的元素。 */
export function useDialog() {
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
  return ref;
}
