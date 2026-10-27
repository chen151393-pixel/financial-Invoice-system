import type { CurrencyEvidence } from "../types";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { Card, CardFooter, CardHeader, Pagination, Segmented } from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import { approveDeclaration, approveDeclarations, queryDeclarations } from "../api";
import { BatchApproveDialog } from "../components/BatchApproveDialog";
import { FinanceSearchForm } from "../components/FinanceSearchForm";
import { FinanceComparison } from "../components/FinanceComparison";
import { ReviewDialog } from "../components/ReviewDialog";
import { ReviewStats } from "../components/ReviewStats";
import type {
  BatchApproveResult,
  ComparisonGroup,
  ComparisonResult,
  ComparisonState,
  DeclarationListQuery,
  ReviewFilter,
} from "../types";

const FILTER_LABELS: Record<ReviewFilter, string> = {
  all: "全部报关单",
  pending: "待审核",
  approved: "审核通过",
};

export function ReviewPage() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState<ComparisonState>({ kind: "loading" });
  const [query, setQuery] = useState<DeclarationListQuery>({
    keyword: searchParams.get("keyword") || "",
    supplierId: "",
    // 工作台"待审批"分区跳转时带 status=pending
    status: searchParams.get("status") === "pending" ? "pending" : "all",
    page: 1,
    pageSize: 20,
  });
  const [refresh, setRefresh] = useState(0);
  // 每次加载成功递增，用于重置列表的展开状态。
  const [loads, setLoads] = useState(0);
  const [suppliers, setSuppliers] = useState<ComparisonResult["suppliers"]>([]);
  // 最近一次成功结果的计数；重新查询时保留，概况卡与状态切换不闪烁
  const [counts, setCounts] = useState<ComparisonResult["counts"] | null>(null);
  const [review, setReview] = useState<ComparisonGroup | null>(null);
  const [batch, setBatch] = useState<ComparisonGroup[] | null>(null);
  const [batchResult, setBatchResult] = useState<BatchApproveResult | null>(null);
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
        const result = await queryDeclarations(query);
        if (active) {
          setState({ kind: "ready", result });
          setLoads((value) => value + 1);
          setSuppliers(result.suppliers || []);
          setCounts(result.counts);
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

  async function approve(note: string, evidence: CurrencyEvidence[]) {
    if (!review || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setApprovalError("");
    try {
      const approved = await approveDeclaration(review.id, review.contentSha256, note, evidence);
      setReview(approved);
      setNotice(
        `${approved.recordNumber} 审核结果已保存，并按供应商自动生成开票任务，可前往「开票跟进」查看。`,
      );
      setRefresh((value) => value + 1);
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : "审核失败，请核实后重试");
    } finally {
      submitLock.current = false;
      setSubmitting(false);
    }
  }
  async function approveBatch(note: string) {
    if (!batch || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setApprovalError("");
    try {
      const result = await approveDeclarations(batch, note);
      setBatchResult(result);
      if (result.approved.length) {
        setNotice(`批量审核：${result.approved.length} 张已审核通过并生成开票任务，可前往「开票跟进」查看。`);
      }
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : "批量审核失败，请刷新后查看结果");
    } finally {
      // 无论结果如何都重新读取：跳过的报关单可能已有新内容，失败时也可能部分已保存
      setRefresh((value) => value + 1);
      submitLock.current = false;
      setSubmitting(false);
    }
  }
  const busy = state.kind === "loading" || submitting;
  return (
    <div className="fr-page">
      {counts && <ReviewStats counts={counts} />}
      <Card className="fr-panel">
        <CardHeader
          title="报关单"
          actions={
            <Segmented
              label="按审核状态筛选"
              value={query.status}
              disabled={busy}
              options={(Object.keys(FILTER_LABELS) as ReviewFilter[]).map((key) => ({
                value: key,
                label: FILTER_LABELS[key],
                count: counts?.[key],
              }))}
              onChange={(status) => setQuery((current) => ({ ...current, status, page: 1 }))}
            />
          }
        />
        <FinanceSearchForm
          initial={{ keyword: query.keyword, supplierId: query.supplierId }}
          busy={busy}
          suppliers={suppliers}
          onSearch={(criteria) => {
            setNotice("");
            setQuery((current) => ({ ...current, ...criteria, page: 1 }));
          }}
        />
        {notice && (
          <p className="fr-status-note" role="status">
            {notice}
          </p>
        )}
        <FinanceComparison
          key={state.kind === "ready" ? `ready-${loads}` : state.kind}
          state={state}
          busy={busy}
          onReview={(group) => {
            setApprovalError("");
            setReview(group);
          }}
          onBatchApprove={(groups) => {
            setApprovalError("");
            setBatchResult(null);
            setBatch(groups);
          }}
          onRetry={() => setRefresh((value) => value + 1)}
          pagination={
            state.kind === "ready" && (
              <CardFooter>
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
              </CardFooter>
            )
          }
        />
      </Card>
      {review && (
        <ReviewDialog
          key={`${review.id}-${review.contentSha256}`}
          group={review}
          busy={submitting}
          error={approvalError}
          onClose={() => {
            if (!submitting) setReview(null);
          }}
          onApprove={(note, evidence) => void approve(note, evidence)}
        />
      )}
      {batch && (
        <BatchApproveDialog
          groups={batch}
          busy={submitting}
          error={approvalError}
          result={batchResult}
          onClose={() => {
            if (!submitting) setBatch(null);
          }}
          onApprove={(note) => void approveBatch(note)}
        />
      )}
    </div>
  );
}
