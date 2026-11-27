import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Alert,
  Button,
  Card,
  CardFooter,
  EmptyState,
  ErrorState,
  Pagination,
  CardHeader,
  Segmented,
  Skeleton,
  StatCard,
  StatGrid,
} from "../../../shared/components/ui";
import { confirmInvoiceBatch, getMatchingQueue, queryInvoiceMatchList } from "../api";
import { uploadInvoiceFiles } from "../api/invoice-file-api";
import { InvoiceFileUploadDialog } from "../components/InvoiceFileUploadDialog";
import { BatchApproveDialog } from "../components/BatchApproveDialog";
import { MatchStatusTable } from "../components/MatchStatusTable";
import { QueueFilters } from "../components/QueueFilters";
import { batchable, QueueTable } from "../components/QueueTable";
import type {
  InvoiceBatchResult,
  InvoiceMatchList,
  InvoiceQueue,
  InvoiceQueueRow,
  MatchPageList,
  QueueQuery,
} from "../types/matching";
import "./matching.css";
import "./matching-parts.css";

type Remote<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };
// 概况卡：待审核与可自动审核走审核队列；未生成建议与已审核通过走发票匹配状态列表
type View = "pending" | "auto" | "none" | "done";
const VIEW_LABELS: Record<View, string> = {
  pending: "待审核发票",
  none: "未生成建议",
  auto: "可自动审核通过",
  done: "已审核通过",
};
const TIERS: [QueueQuery["tier"], string][] = [
  ["all", "全部发票"],
  ["high", "高置信度"],
  ["medium", "中置信度"],
  ["low", "低置信度"],
];
const LIST_PAGE_SIZE = 20;
// 发票匹配状态列表按单个号码 / 名称部分匹配；多条用逗号分隔的条件只在审核队列中生效
const single = (value: string) => (/[,，\s]/.test(value.trim()) ? "" : value.trim());

export function MatchingQueuePage() {
  // 工作台"高置信度可批量通过"带 ?tier=high 进入；?view=auto 等直接打开对应概况卡
  const [searchParams] = useSearchParams();
  const initialView = (["pending", "auto", "none", "done"] as const).find(
    (value) => value === searchParams.get("view"),
  );
  const [view, setView] = useState<View>(initialView ?? "pending");
  const [query, setQuery] = useState<QueueQuery>({
    tier: TIERS.find(([tier]) => tier === searchParams.get("tier"))?.[0] ?? "all",
    view: initialView === "auto" ? "auto" : "pending",
    anomaly: "all",
    supplierId: "",
    invoiceNo: searchParams.get("invoiceNo") || "",
    supplierName: searchParams.get("supplierName") || "",
    invoiceFrom: "",
    invoiceTo: "",
    page: 1,
    pageSize: 20,
  });
  const [listPage, setListPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<Remote<InvoiceQueue>>({ kind: "loading" });
  const [list, setList] = useState<Remote<InvoiceMatchList<MatchPageList>>>({ kind: "loading" });
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);
  const [batchRows, setBatchRows] = useState<InvoiceQueueRow[] | null>(null);
  const [batchResult, setBatchResult] = useState<InvoiceBatchResult | null>(null);
  const [batchError, setBatchError] = useState("");
  const listed = view === "none" || view === "done";

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      try {
        const data = await getMatchingQueue(query, controller.signal);
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "审核队列读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [query, refresh]);

  // 未生成建议、已审核通过的张数与列表来自发票匹配状态（已排除红字、作废等不参与比对的发票）
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      try {
        const data = await queryInvoiceMatchList<MatchPageList>(
          {
            invoice_no: single(query.invoiceNo),
            seller_name: single(query.supplierName),
            account: "",
            status: "",
            date_from: query.invoiceFrom,
            date_to: query.invoiceTo,
            matchStatus: view === "none" ? "none" : view === "done" ? "confirmed" : "all",
            page: listed ? listPage : 1,
            pageSize: listed ? LIST_PAGE_SIZE : 1,
          },
          controller.signal,
        );
        if (active) setList({ kind: "ready", data });
      } catch (error) {
        if (active)
          setList({ kind: "error", message: error instanceof Error ? error.message : "发票列表读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [
    query.invoiceNo,
    query.supplierName,
    query.invoiceFrom,
    query.invoiceTo,
    view,
    listed,
    listPage,
    refresh,
  ]);

  function change(patch: Partial<QueueQuery>) {
    if (busy) return;
    setSelected([]);
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  }
  function pick(next: View) {
    if (busy) return;
    setView(next);
    setListPage(1);
    setList({ kind: "loading" });
    change({ view: next === "auto" ? "auto" : "pending", tier: "all" });
  }
  async function confirmSelected(note: string) {
    if (busy || !batchRows?.length || batchResult || batchError) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await confirmInvoiceBatch(batchRows, note);
      setBatchResult(result);
      setFeedback({
        error: result.skipped.length > 0,
        text: `已通过 ${result.approved.length} 张发票，跳过 ${result.skipped.length} 张。`,
      });
    } catch (error) {
      const message = `${error instanceof Error ? error.message : "批量审核请求失败"}；部分发票可能已完成审核，请刷新核实后再操作。`;
      setBatchError(message);
      setFeedback({ error: true, text: message });
    } finally {
      setSelected([]);
      setState({ kind: "loading" });
      setRefresh((value) => value + 1);
      setBusy(false);
    }
  }

  const data = state.kind === "ready" ? state.data : null;
  const listData = list.kind === "ready" ? list.data : null;
  const chosen = data?.rows.filter((row) => selected.includes(row.invoice.id) && batchable(row)) ?? [];
  // 可自动审核视图未勾选时，按本页全部可批量发票提交；后端仍逐张复核
  const targets = chosen.length > 0 ? chosen : view === "auto" ? (data?.rows.filter(batchable) ?? []) : [];
  const tierLabel = TIERS.find(([tier]) => tier === query.tier)?.[1];
  return (
    <div className="matching-page">
      {batchRows && (
        <BatchApproveDialog
          rows={batchRows}
          busy={busy}
          result={batchResult}
          error={batchError}
          onClose={() => setBatchRows(null)}
          onApprove={(note) => void confirmSelected(note)}
        />
      )}
      {uploading && (
        <InvoiceFileUploadDialog upload={uploadInvoiceFiles} onClose={() => setUploading(false)} />
      )}
      <StatGrid label="比对概况">
        <StatCard
          glyph="审"
          tone={data && data.counts.pending > 0 ? "warning" : "neutral"}
          label="待审核发票"
          value={data ? `${data.counts.pending} 张` : "—"}
          note="置信度按待审核明细最低值分档"
          selected={view === "pending"}
          disabled={busy}
          onSelect={() => pick("pending")}
        />
        <StatCard
          glyph="未"
          label="未生成建议"
          value={listData ? `${listData.counts.none} 张` : "—"}
          note="没有可审核的建议，可进入详情手动关联"
          selected={view === "none"}
          disabled={busy}
          onSelect={() => pick("none")}
        />
        <StatCard
          glyph="自"
          tone="primary"
          label="可自动审核通过"
          value={data ? `${data.counts.auto} 张` : "—"}
          note="置信度 100% 且无需异常说明，可批量审核"
          selected={view === "auto"}
          disabled={busy}
          onSelect={() => pick("auto")}
        />
        <StatCard
          glyph="通"
          label="已审核通过"
          value={listData ? `${listData.counts.confirmed} 张` : "—"}
          note="已整单通过，收票进度已更新到开票任务"
          selected={view === "done"}
          disabled={busy}
          onSelect={() => pick("done")}
        />
      </StatGrid>
      <Card className="matching-queue" aria-labelledby="matching-queue-title">
        <CardHeader
          title={
            <span id="matching-queue-title">
              比对发票 · {VIEW_LABELS[view]}
              {!listed && query.tier !== "all" ? ` · ${tierLabel}` : ""}
            </span>
          }
          actions={
            <span className="matching-row">
              <Segmented
                label="按置信度筛选"
                value={listed ? "all" : query.tier}
                disabled={busy || listed}
                options={TIERS.map(([tier, label]) => ({
                  value: tier,
                  label,
                  count: listed ? undefined : data?.counts[tier],
                }))}
                onChange={(tier) => change({ tier })}
              />
              <Button disabled={busy} onClick={() => setUploading(true)}>
                批量上传发票文件
              </Button>
              <Button
                disabled={busy}
                onClick={() => {
                  setSelected([]);
                  setState({ kind: "loading" });
                  setList({ kind: "loading" });
                  setRefresh((value) => value + 1);
                }}
              >
                刷新
              </Button>
            </span>
          }
        />
        <QueueFilters
          value={{
            anomaly: query.anomaly,
            invoiceNo: query.invoiceNo,
            supplierName: query.supplierName,
            invoiceFrom: query.invoiceFrom,
            invoiceTo: query.invoiceTo,
          }}
          busy={busy || state.kind === "loading"}
          onApply={(filters) => {
            setListPage(1);
            change(filters);
          }}
          batchAction={
            listed ? undefined : (
              <Button
                variant={targets.length > 0 ? "primary" : "secondary"}
                disabled={busy || targets.length === 0}
                aria-describedby="matching-batch-hint"
                onClick={() => {
                  setBatchResult(null);
                  setBatchError("");
                  setBatchRows(targets);
                }}
              >
                {busy ? "审核中…" : `批量审核通过${targets.length ? `（${targets.length}）` : ""}`}
              </Button>
            )
          }
        />
        <div className="matching-body">
          {listed ? (
            <>
              {listData?.notice && <Alert tone="info">{listData.notice}</Alert>}
              {list.kind === "loading" && <Skeleton label="正在读取发票" rows={2} />}
              {list.kind === "error" && (
                <ErrorState
                  title="发票列表暂时无法加载"
                  message={list.message}
                  action={<Button onClick={() => setRefresh((value) => value + 1)}>重新加载</Button>}
                />
              )}
              {listData && listData.list.rows.length === 0 && (
                <EmptyState
                  icon="check"
                  title={view === "none" ? "没有未生成建议的发票" : "还没有审核通过的发票"}
                  description="红字、已被红冲、作废等发票不参与比对，可在进项发票中查看。"
                />
              )}
              {listData && listData.list.rows.length > 0 && (
                <MatchStatusTable rows={listData.list.rows} summaries={listData.summaries} />
              )}
            </>
          ) : (
            <>
              <p id="matching-batch-hint" className="matching-help">
                {view === "auto"
                  ? "本页均为置信度 100% 且无需异常说明的发票；不勾选时批量审核本页全部发票，提交后系统逐张复核。"
                  : "勾选当前页置信度为 100% 且可审核的发票后，可批量审核通过。"}
              </p>
              {data?.notice && <Alert tone="info">{data.notice}</Alert>}
              {feedback && <Alert tone={feedback.error ? "danger" : "success"}>{feedback.text}</Alert>}
              {selected.length > 0 && (
                <div className="matching-selection" role="status">
                  <span>
                    <strong>当前页已选 {selected.length} 张</strong> · 将审核所选发票的全部待审核建议
                  </span>
                  <span className="matching-row">
                    <Button disabled={busy} onClick={() => setSelected([])}>
                      取消选择
                    </Button>
                  </span>
                </div>
              )}
              {state.kind === "loading" && <Skeleton label="正在读取待审核建议" rows={2} />}
              {state.kind === "error" && (
                <ErrorState
                  title="审核队列暂时无法加载"
                  message={state.message}
                  action={<Button onClick={() => setRefresh((value) => value + 1)}>重新加载</Button>}
                />
              )}
              {data && data.rows.length === 0 && (
                <EmptyState
                  icon="check"
                  title={view === "auto" ? "没有可自动审核通过的发票" : "没有待审核的比对建议"}
                  description="导入发票后，系统会为已审核的子采购行自动生成建议。"
                />
              )}
              {data && data.rows.length > 0 && (
                <QueueTable
                  rows={data.rows}
                  busy={busy}
                  selected={selected}
                  onToggle={(id, checked) =>
                    setSelected((current) =>
                      checked ? [...current, id] : current.filter((value) => value !== id),
                    )
                  }
                  onToggleAll={(checked) =>
                    setSelected(checked ? data.rows.filter(batchable).map((row) => row.invoice.id) : [])
                  }
                />
              )}
            </>
          )}
        </div>
        {!listed && data && (
          <CardFooter>
            <Pagination
              label="审核队列分页"
              total={data.total}
              unit="张"
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[10, 20, 50]}
              disabled={busy}
              onPageChange={(page) => {
                setSelected([]);
                setState({ kind: "loading" });
                setQuery((current) => ({ ...current, page }));
              }}
              onPageSizeChange={(pageSize) => change({ pageSize })}
            />
          </CardFooter>
        )}
        {listed && listData && (
          <CardFooter>
            <Pagination
              label="发票列表分页"
              total={listData.list.total}
              unit="张"
              page={listData.list.page}
              pageCount={Math.max(1, Math.ceil(listData.list.total / LIST_PAGE_SIZE))}
              pageSize={LIST_PAGE_SIZE}
              pageSizes={[LIST_PAGE_SIZE]}
              onPageChange={(page) => {
                setList({ kind: "loading" });
                setListPage(page);
              }}
              onPageSizeChange={() => {}}
            />
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
