import { useRef, useState } from "react";
import { createPreview, isNotConnected } from "../api";

/**
 * 生成预览。同一张发票在得到结果前重复点击或网络中断后重试，沿用同一请求编号，
 * 后端据此返回原预览而不是再生成一份。
 */
export function useCreatePreview(onCreated: (requestId: string) => void) {
  const pending = useRef(new Map<string, string>());
  const [busyInvoice, setBusyInvoice] = useState("");
  const [error, setError] = useState<{ invoiceId: string; message: string } | null>(null);
  return {
    busyInvoice,
    error,
    create: async (invoiceId: string) => {
      const requestId = pending.current.get(invoiceId) ?? crypto.randomUUID();
      pending.current.set(invoiceId, requestId);
      setBusyInvoice(invoiceId);
      setError(null);
      try {
        const preview = await createPreview(invoiceId, requestId);
        pending.current.delete(invoiceId);
        onCreated(preview.requestId);
      } catch (failure) {
        setError({
          invoiceId,
          message: isNotConnected(failure)
            ? "生成预览接口尚未接入，未创建任何预览"
            : failure instanceof Error
              ? failure.message
              : "生成预览失败，请稍后重试",
        });
      } finally {
        setBusyInvoice("");
      }
    },
  };
}
