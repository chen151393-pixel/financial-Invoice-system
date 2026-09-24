import { useEffect, useRef, useState } from "react";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import { approveDeclaration, listFinanceDeclarations } from "../api";
import { FinanceSearchForm } from "../components/FinanceSearchForm";
import { FinanceComparison } from "../components/FinanceComparison";
import { ReviewDialog } from "../components/ReviewDialog";
import type { ComparisonGroup, ComparisonState, DeclarationListQuery } from "../types";

export function FinanceReconciliationPage() {
  const [state, setState] = useState<ComparisonState>({ kind: "loading" });
  const [query, setQuery] = useState<DeclarationListQuery>({
    keyword: "",
    account: "",
    status: "all",
    page: 1,
    pageSize: 20,
  });
  const [refresh, setRefresh] = useState(0);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [review, setReview] = useState<ComparisonGroup | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [approvalError, setApprovalError] = useState("");
  const [notice, setNotice] = useState("");
  const submitLock = useRef(false);
  useEffect(() => {
    let active = true;
    async function load() {
      setState({ kind: "loading" });
      try {
        await openLocalSession();
        const result = await listFinanceDeclarations(query);
        if (active) {
          setState({ kind: "ready", result });
          setAccounts(result.accounts || []);
        }
      } catch (error) {
        if (active)
          setState({
            kind: "error",
            message: error instanceof Error ? error.message : "加载失败，请稍后重试",
          });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);

  async function approve(note: string) {
    if (!review || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setApprovalError("");
    try {
      const approved = await approveDeclaration(review.snapshotId, note);
      setReview(approved);
      setNotice(
        `${approved.recordNumber} 审核结果已保存${approved.invoiceTaskCount != null ? `，关联 ${approved.invoiceTaskCount} 个开票任务，可前往「开票跟进」查看` : ""}。`,
      );
      setRefresh((value) => value + 1);
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : "审核失败，请核实后重试");
    } finally {
      submitLock.current = false;
      setSubmitting(false);
    }
  }
  return (
    <>
      <FinanceSearchForm
        busy={state.kind === "loading" || submitting}
        accounts={accounts}
        onSearch={(keyword, account) => {
          setNotice("");
          setQuery((current) => ({ ...current, keyword, account, status: "all", page: 1 }));
        }}
        onRefresh={() => setRefresh((value) => value + 1)}
      />
      {notice && (
        <p className="fr-status-note" role="status">
          {notice}
        </p>
      )}
      <FinanceComparison
        key={state.kind === "ready" ? state.result.requestId : state.kind}
        state={state}
        filter={query.status}
        onFilter={(status) => setQuery((current) => ({ ...current, status, page: 1 }))}
        onReview={(group) => {
          setApprovalError("");
          setReview(group);
        }}
        onRetry={() => setRefresh((value) => value + 1)}
        pagination={
          state.kind === "ready" && (
            <Pagination
              label="报关单分页"
              total={state.result.total ?? 0}
              page={state.result.page ?? query.page}
              pageCount={state.result.pages ?? 1}
              pageSize={state.result.pageSize ?? query.pageSize}
              pageSizes={[10, 20, 50]}
              disabled={submitting}
              onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
              onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
            />
          )
        }
      />
      {review && (
        <ReviewDialog
          key={review.snapshotId}
          group={review}
          busy={submitting}
          error={approvalError}
          onClose={() => {
            if (!submitting) setReview(null);
          }}
          onApprove={(note) => void approve(note)}
        />
      )}
    </>
  );
}
