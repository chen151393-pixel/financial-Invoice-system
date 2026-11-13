import { useRef, useState } from "react";
import { previewOwnerChange, saveOwnerChange } from "../api/supplier-owner";
import type { OwnerChange, OwnerImpact } from "../types/supplier-owner";

export function useOwnerChange(onSaved: (message: string) => void) {
  const [preview, setPreview] = useState<OwnerImpact | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const draft = useRef<OwnerChange | null>(null);
  function invalidate() {
    setPreview(null);
    draft.current = null;
    setError("");
  }
  async function inspect(value: OwnerChange) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const result = await previewOwnerChange(value);
      draft.current = value;
      setPreview(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "预览失败，请重试");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function save() {
    if (lock.current || !preview || !draft.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await saveOwnerChange(draft.current, preview.previewToken);
      setPreview(null);
      draft.current = null;
      onSaved(`已保存 ${result.saved} 条人员关联，交接 ${result.transferredTasks} 个未完成任务。`);
    } catch (error) {
      setPreview(null);
      setError(error instanceof Error ? error.message : "保存失败，请刷新核实后重新预览");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { preview, error, busy, invalidate, inspect, save };
}
