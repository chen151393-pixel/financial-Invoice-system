import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardFooter,
  EmptyState,
  ErrorState,
  Pagination,
  SectionTitle,
  Skeleton,
  Tabs,
} from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import { confirmBatch, getMatchingQueue } from "../api";
import { uploadInvoiceFiles } from "../api/invoice-file-api";
import { InvoiceFileUploadDialog } from "../components/InvoiceFileUploadDialog";
import { QueueFilters } from "../components/QueueFilters";
import { batchable, QueueTable } from "../components/QueueTable";
import type { Queue, QueueQuery } from "../types/matching";
import "./matching.css";
import "./matching-parts.css";

type Remote = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: Queue };
const TABS: [QueueQuery["tier"], string][] = [
  ["all", "全部建议"],
  ["high", "高置信度"],
  ["medium", "中置信度"],
  ["low", "低置信度"],
];

export function MatchingQueuePage() {
  const [query, setQuery] = useState<QueueQuery>({
    tier: "all",
    anomaly: "all",
    supplierId: "",
    invoiceFrom: "",
    invoiceTo: "",
    page: 1,
    pageSize: 20,
  });
  const [suppliers, setSuppliers] = useState<{ id: string; name: string }[]>([]);
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
          setSuppliers(data.suppliers ?? []);
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
    setBusy(true);
    setFeedback(null);
    try {
      const result = await confirmBatch(selected);
      const skipped = result.skipped.map((item) => item.reason).join("；");
      setFeedback({
        error: result.skipped.length > 0,
        text: `已通过 ${result.confirmed} 条${result.skipped.length ? `，跳过 ${result.skipped.length} 条：${skipped}` : "。"}`,
      });
      setSelected([]);
      setRefresh((value) => value + 1);
    } catch (error) {
      setFeedback({
        error: true,
        text: error instanceof Error ? error.message : "批量通过失败，请刷新后核对",
      });
    } finally {
      setBusy(false);
    }
  }

  const data = state.kind === "ready" ? state.data : null;
  return (
    <div className="matching-page">
      <QueueFilters
        value={{
          anomaly: query.anomaly,
          supplierId: query.supplierId,
          invoiceFrom: query.invoiceFrom,
          invoiceTo: query.invoiceTo,
        }}
        suppliers={suppliers}
        busy={busy || state.kind === "loading"}
        onApply={(filters) => change(filters)}
      />
      <SectionTitle
        id="matching-queue-title"
        title="待审核比对建议"
        count={data ? `共 ${data.total} 条` : undefined}
        actions={
          <span className="matching-row">
            <Button disabled={busy} onClick={() => setUploading(true)}>
              批量上传发票文件
            </Button>
            <Button disabled={busy} onClick={() => setRefresh((value) => value + 1)}>
              刷新
            </Button>
          </span>
        }
      />
      {uploading && (
        <InvoiceFileUploadDialog upload={uploadInvoiceFiles} onClose={() => setUploading(false)} />
      )}
      <Card className="matching-queue" aria-labelledby="matching-queue-title">
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
          {feedback && <Alert tone={feedback.error ? "warning" : "success"}>{feedback.text}</Alert>}
          {selected.length > 0 && (
            <div className="matching-selection" role="status">
              <span>
                <strong>已选 {selected.length} 条</strong> · 仅高置信度且比对项全部一致的建议可勾选
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
              selected={selected}
              onToggle={(id, checked) =>
                setSelected((current) =>
                  checked ? [...current, id] : current.filter((value) => value !== id),
                )
              }
              onToggleAll={(checked) =>
                setSelected(checked ? data.rows.filter(batchable).map((row) => row.allocation.id) : [])
              }
            />
          )}
        </div>
        {data && (
          <CardFooter>
            <Pagination
              label="审核队列分页"
              total={data.total}
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[10, 20, 50]}
              disabled={busy}
              onPageChange={(page) => {
                setSelected([]);
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
