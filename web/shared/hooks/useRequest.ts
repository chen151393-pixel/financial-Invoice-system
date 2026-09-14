import { useRef, useState } from "react";

/** 只管理请求状态；互斥标记避免一次渲染前连点造成重复派发。 */
export function useRequest() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const pending = useRef(false);
  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "请求失败");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return { busy, message, setMessage, run };
}
