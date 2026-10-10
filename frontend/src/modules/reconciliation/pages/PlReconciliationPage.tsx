import { useEffect, useRef, useState } from "react";
import { openLocalSession } from "../../identity/api";
import { queryPlSourceComparison } from "../api";
import { PlSearchForm, type PlSearchCriteria } from "../components/PlSearchForm";
import { PlSourceComparison } from "../components/PlSourceComparison";
import type { SourceComparisonState } from "../source-types";

export function PlReconciliationPage() {
  const [state, setState] = useState<SourceComparisonState>({ kind: "idle" });
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
      await openLocalSession();
      const result = await queryPlSourceComparison(criteria);
      if (current === requestId.current) setState({ kind: "ready", result });
    } catch (error) {
      if (current === requestId.current)
        setState({ kind: "error", message: error instanceof Error ? error.message : "查询失败，请重试" });
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
        submitLabel="查询"
      />
      <PlSourceComparison
        state={state}
        onRetry={() => {
          if (lastQuery.current) void search(lastQuery.current);
        }}
      />
    </>
  );
}
