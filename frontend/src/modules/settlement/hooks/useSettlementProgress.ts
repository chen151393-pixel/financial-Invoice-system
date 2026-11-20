import { useEffect, useState } from "react";
import { querySettlementProgress } from "../api/progress-api";
import type { SettlementProgress } from "../types/progress";
type State = { kind: "ready"; result: SettlementProgress } | { kind: "error"; message: string };
export function useSettlementProgress(consignee: string, currency: string, revision: string) {
  const key = JSON.stringify([consignee, currency, revision]);
  const [snapshot, setSnapshot] = useState<{ key: string; state: State }>();
  useEffect(() => {
    const controller = new AbortController();
    querySettlementProgress({ consignee, currency }, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setSnapshot({ key, state: { kind: "ready", result } });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setSnapshot({
            key,
            state: { kind: "error", message: error instanceof Error ? error.message : "结汇进度读取失败" },
          });
      });
    return () => controller.abort();
  }, [key, consignee, currency]);
  return snapshot?.key === key ? snapshot.state : { kind: "loading" as const };
}
