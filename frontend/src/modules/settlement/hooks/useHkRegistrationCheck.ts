import { useEffect, useState } from "react";
import { checkHkRegistration } from "../api/hk-receipt-api";
import type { HkRegistrationCheck } from "../types/hk-receipt";
export function useHkRegistrationCheck(numbers: string[], amount: string, fee: string, date: string) {
  const key = JSON.stringify([numbers, amount || "0", fee || "0", date || null]);
  const [snapshot, setSnapshot] = useState<{
    key: string;
    result: HkRegistrationCheck | null;
    error: string;
  }>({ key: "", result: null, error: "" });
  useEffect(() => {
    const controller = new AbortController();
    const [declarationNos, receivedAmount, receivedFee, receivedOn] = JSON.parse(key) as [
      string[],
      string,
      string,
      string | null,
    ];
    const timer = setTimeout(() => {
      checkHkRegistration({ declarationNos, receivedAmount, receivedFee, receivedOn }, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) setSnapshot({ key, result, error: "" });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setSnapshot({
              key,
              result: null,
              error: error instanceof Error ? error.message : "核对失败，请修改输入后重试",
            });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [key]);
  return {
    result: snapshot.result,
    error: snapshot.key === key ? snapshot.error : "",
    loading: snapshot.key !== key,
  };
}
