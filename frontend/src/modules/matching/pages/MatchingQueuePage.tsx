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
  Skeleton,
  Tabs,
} from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import { confirmInvoiceBatch, getMatchingQueue } from "../api";
import { uploadInvoiceFiles } from "../api/invoice-file-api";
import { InvoiceFileUploadDialog } from "../components/InvoiceFileUploadDialog";
import { BatchApproveDialog } from "../components/BatchApproveDialog";
import { QueueFilters } from "../components/QueueFilters";
import { batchable, QueueTable } from "../components/QueueTable";
import type { InvoiceBatchResult, InvoiceQueue, InvoiceQueueRow, QueueQuery } from "../types/matching";
import "./matching.css";
import "./matching-parts.css";

type Remote =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: InvoiceQueue };
const TABS: [QueueQuery["tier"], string][] = [
  ["all", "全部发票"],
  ["high", "高置信度"],
  ["medium", "中置信度"],
  ["low", "低置信度"],
];

export function MatchingQueuePage() {
  // 工作台"高置信度可批量通过"带 ?tier=high 进入，只用作初始分档
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState<QueueQuery>({
    tier: TABS.find(([tier]) => tier === searchParams.get("tier"))?.[0] ?? "all",
    anomaly: "all",
    supplierId: "",
    invoiceNo: searchParams.get("invoiceNo") || "",
    supplierName: searchParams.get("supplierName") || "",
    invoiceFrom: "",
    invoiceTo: "",
    page: 1,
    pageSize: 20,
  });
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);
  const [batchRows, setBatchRows] = useState<InvoiceQueueRow[] | null>(null);
  const [batchResult, setBatchResult] = useState<InvoiceBatchResult | null>(null);
  const [batchError, setBatchError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getMatchingQueue(query);
        if (active) {
          setState({ kind: "ready", data });
        }
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "审核队列读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);

  function change(patch: Partial<QueueQuery>) {
    if (busy) return;
    setSelected([]);
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
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
  const chosen = data?.rows.filter((row) => selected.includes(row.invoice.id) && batchable(row)) ?? [];
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
      <Card className="matching-queue" aria-labelledby="matching-queue-title">
        <CardHeader
          title={<span id="matching-queue-title">待审核发票</span>}
          description={
            data ? `共 ${data.total} 张 · 每张发票统一核对，置信度按待审核明细最低值分档` : undefined
          }
          actions={
            <span className="matching-row">
              <Button disabled={busy} onClick={() => setUploading(true)}>
                批量上传发票文件
              </Button>
              <Button
                disabled={busy}
                onClick={() => {
                  setSelected([]);
                  setState({ kind: "loading" });
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
          onApply={(filters) => change(filters)}
          batchAction={
            <Button
              disabled={busy || chosen.length === 0}
              aria-describedby="matching-batch-hint"
              onClick={() => {
                setBatchResult(null);
                setBatchError("");
                setBatchRows(chosen);
              }}
            >
              {busy ? "审核中…" : `批量审核通过${chosen.length ? `（${chosen.length}）` : ""}`}
            </Button>
          }
        />
        <div className="matching-queue__tabs">
          <Tabs
            label="按置信度筛选"
            value={query.tier}
            onChange={(tier) => change({ tier })}
            items={TABS.map(([tier, label]) => ({ key: tier, label, count: data?.counts[tier] }))}
          />
        </div>
        <div className="matching-body">
          <p id="matching-batch-hint" className="matching-help">
            勾选当前页置信度为 100% 且可审核的发票后，可批量审核通过。
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
              title="没有待审核的比对建议"
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
        </div>
        {data && (
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
      </Card>
    </div>
  );
}
