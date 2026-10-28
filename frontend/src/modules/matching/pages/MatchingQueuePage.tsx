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
import { confirmBatch, getMatchingQueue } from "../api";
import { uploadInvoiceFiles } from "../api/invoice-file-api";
import { InvoiceFileUploadDialog } from "../components/InvoiceFileUploadDialog";
import { QueueFilters } from "../components/QueueFilters";
import { batchable, QueueTable } from "../components/QueueTable";
import type { InvoiceQueue, QueueQuery } from "../types/matching";
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
    setSelected([]);
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  }
  async function confirmSelected() {
    if (busy) return;
    setBusy(true);
    setFeedback(null);
    let confirmed = 0;
    const skipped: string[] = [];
    try {
      const ids =
        state.kind === "ready"
          ? state.data.rows.filter((row) => selected.includes(row.invoice.id)).flatMap((row) => row.batchIds)
          : [];
      // 保持现有每次最多 100 条的接口约束；失败停止后续提交，不自动重发。
      for (let start = 0; start < ids.length; start += 100) {
        const result = await confirmBatch(ids.slice(start, start + 100));
        confirmed += result.confirmed;
        skipped.push(...result.skipped.map((item) => item.reason));
      }
      setFeedback({
        error: skipped.length > 0,
        text: `已通过 ${confirmed} 条建议${skipped.length ? `，跳过 ${skipped.length} 条：${skipped.join("；")}` : "。"}`,
      });
    } catch (error) {
      setFeedback({
        error: true,
        text: `已收到成功结果 ${confirmed} 条建议。${error instanceof Error ? error.message : "批量通过失败"}；后续提交已停止，请刷新核对当前结果。`,
      });
    } finally {
      setSelected([]);
      setState({ kind: "loading" });
      setRefresh((value) => value + 1);
      setBusy(false);
    }
  }

  const data = state.kind === "ready" ? state.data : null;
  return (
    <div className="matching-page">
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
          {data?.notice && <Alert tone="info">{data.notice}</Alert>}
          {feedback && <Alert tone={feedback.error ? "danger" : "success"}>{feedback.text}</Alert>}
          {selected.length > 0 && (
            <div className="matching-selection" role="status">
              <span>
                <strong>已选 {selected.length} 张</strong> · 批量通过所选发票的全部待审核建议
              </span>
              <span className="matching-row">
                <Button disabled={busy} onClick={() => setSelected([])}>
                  取消选择
                </Button>
                <Button variant="primary" disabled={busy} onClick={() => void confirmSelected()}>
                  {busy ? "处理中…" : `批量通过（${selected.length}）`}
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
