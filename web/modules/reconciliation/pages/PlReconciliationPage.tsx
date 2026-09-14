import { useEffect, useRef, useState } from "react";
import { openLocalSession } from "../../identity/api";
import { queryPlComparison } from "../api";
import { PlSearchForm, type PlSearchCriteria } from "../components/PlSearchForm";
import { PlComparison } from "../components/PlComparison";
import type { ComparisonState } from "../types";

export function PlReconciliationPage() {
  const [state, setState] = useState<ComparisonState>({ kind: "idle" });
  const requestId = useRef(0);
  const lastQuery = useRef<PlSearchCriteria | null>(null);
  useEffect(
    () => () => {
      requestId.current += 1;
    },
    [],
  );

  async function search(criteria: PlSearchCriteria) {
    const current = ++requestId.current;
    lastQuery.current = criteria;
    setState({ kind: "loading" });
    try {
      // 复用现有本机会话及后端M2M权限校验；浏览器不接触NS凭证。
      await openLocalSession();
      const result = await queryPlComparison(criteria);
      if (current === requestId.current) setState({ kind: "ready", result });
    } catch (error) {
      if (current === requestId.current)
        setState({ kind: "error", message: error instanceof Error ? error.message : "拉取失败，请稍后重试" });
    }
  }
  return (
    <>
      <PlSearchForm
        onSearch={(criteria) => void search(criteria)}
        onReset={() => {
          requestId.current += 1;
          lastQuery.current = null;
          setState({ kind: "idle" });
        }}
        busy={state.kind === "loading"}
        submitLabel="从 NS 拉取"
      />
      <PlComparison
        state={state}
        onRetry={() => {
          if (lastQuery.current) void search(lastQuery.current);
        }}
      />
    </>
  );
}
