import { useEffect, useState } from "react";
import { getFeishuOutcome, getLoginOptions } from "../api";
import type { LoginOptions } from "../types";

/** 登录页可用的登录方式，以及本浏览器上一次飞书登录的失败原因。 */
export function useLoginOptions(enabled: boolean) {
  const [options, setOptions] = useState<LoginOptions | null>(null);
  const [failure, setFailure] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    getLoginOptions()
      .then((value) => {
        if (active) setOptions(value);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : "无法读取登录方式");
      });
    getFeishuOutcome()
      .then((outcome) => {
        if (active && outcome.status === "failed" && outcome.reason) setFailure(outcome.reason);
      })
      // 读取失败原因只是辅助信息，失败时不影响登录
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [enabled]);

  return { options, failure, loadError };
}
