import { useEffect, useState } from "react";
import { previewHkReceipt } from "../api/hk-workbench-api";
import type { HkReceiptCheck } from "../types/hk-workbench";
export function useHkReceiptPreview(numbers: string[], amount: string, fee: string) {
  const key = JSON.stringify([numbers, amount, fee]);
  const [snapshot, setSnapshot] = useState<{ key: string; result: HkReceiptCheck | null; error: string }>({
    key: "",
    result: null,
    error: "",
  });
  useEffect(() => {
    const controller = new AbortController();
    const [selected, arrived, commission] = JSON.parse(key) as [string[], string, string];
    const timer = setTimeout(() => {
      previewHkReceipt(selected, arrived || "0", commission || "0", controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) setSnapshot({ key, result, error: "" });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setSnapshot({
              key,
              result: null,
              error: error instanceof Error ? error.message : "金额核对失败",
            });
        });
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key]);
  return snapshot.key === key
    ? { loading: false, result: snapshot.result, error: snapshot.error }
    : { loading: true, result: null, error: "" };
}
