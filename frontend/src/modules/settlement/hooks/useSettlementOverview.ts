import { useEffect, useState } from "react";
import { queryOverview } from "../api/overview-api";
import type { OverviewList, OverviewQuery } from "../types/overview";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: OverviewList }
  | { kind: "error"; message: string };

export function useSettlementOverview(query: OverviewQuery) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryOverview(query, controller.signal);
        if (!controller.signal.aborted) setState({ kind: "ready", result });
      } catch (reason) {
        if (!controller.signal.aborted) {
          setState({ kind: "error", message: reason instanceof Error ? reason.message : "收汇总览读取失败" });
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  return { state, reload: () => setRefresh((value) => value + 1), revision: refresh };
}
