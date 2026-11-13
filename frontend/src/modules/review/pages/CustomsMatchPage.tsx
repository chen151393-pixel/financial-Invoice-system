import { useEffect, useState } from "react";
import {
  Button,
  Card,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Pagination,
  Segmented,
  Skeleton,
} from "../../../shared/components/ui";
import { CustomsApproveDialog } from "../components/CustomsApproveDialog";
import { CustomsImportDialog } from "../components/CustomsImportDialog";
import { CustomsReceiptRow } from "../components/CustomsReceiptRow";
import { CustomsSearchForm, EMPTY_CUSTOMS_SEARCH } from "../components/CustomsSearchForm";
import { CustomsStats } from "../components/CustomsStats";
import { ReviewListToolbar } from "../components/ReviewListToolbar";
import { queryCustomsReceipts } from "../customs-api";
import type {
  CustomsCounts,
  CustomsFilter,
  CustomsReceipt,
  CustomsReceiptList,
  CustomsReceiptQuery,
} from "../customs-types";
import "../components/review.css";
import "../components/customs-match.css";

type ListState =
  | { kind: "loading" }
  | { kind: "ready"; result: CustomsReceiptList }
  | { kind: "error"; message: string };

const FILTERS: readonly { value: CustomsFilter; label: string; count: (c: CustomsCounts) => number }[] = [
  { value: "all", label: "全部", count: (c) => c.receipts },
  { value: "matched", label: "一致", count: (c) => c.matched },
  { value: "different", label: "有差异", count: (c) => c.different },
  { value: "ns_missing", label: "未找到 NS", count: (c) => c.nsMissing },
];
const TITLES: Record<CustomsFilter, string> = {
  all: "报关单匹配",
  matched: "报关单匹配 · 一致",
  different: "报关单匹配 · 有差异",
  ns_missing: "报关单匹配 · 未找到 NS 报关单",
};
const COLUMN_WIDTHS = [20, 9, 5, 12, 20, 15, 10, 9];
const BATCH_WIDTHS = [3, 20, 9, 5, 12, 17, 15, 10, 9];

/** 海关审核沿用财务核对的查询、列表工具栏、批量选择和行操作布局。 */
export function CustomsMatchPage() {
  const [query, setQuery] = useState<CustomsReceiptQuery>({
    ...EMPTY_CUSTOMS_SEARCH,
    status: "all",
    page: 1,
    pageSize: 20,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [counts, setCounts] = useState<CustomsCounts | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [expanded, setExpanded] = useState<number[]>([]);
  const [importing, setImporting] = useState(false);
  const [batch, setBatch] = useState(false);
  const [selection, setSelection] = useState<number[]>([]);
  const [approval, setApproval] = useState<CustomsReceipt[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      setSelection([]);
      try {
        const result = await queryCustomsReceipts(query, controller.signal);
        setState({ kind: "ready", result });
        setCounts(result.counts);
        setExpanded(result.items.filter((item) => item.status === "different").map((item) => item.id));
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  const busy = state.kind === "loading" || !!approval;
  const items = state.kind === "ready" ? state.result.items : [];
  const selectable = items.filter((item) => item.approval.allowed);
  const chosen = selectable.filter((item) => selection.includes(item.id));
  const setStatus = (status: CustomsFilter) => setQuery((current) => ({ ...current, status, page: 1 }));
  const reload = () => setRefresh((value) => value + 1);
  return (
    <div className="fr-page cm-page">
      {counts && <CustomsStats counts={counts} value={query.status} onSelect={setStatus} />}
      <Card className="fr-panel">
        <CardHeader
          title={TITLES[query.status]}
          actions={
            <div className="cm-actions">
              <Segmented
                label="按比对结果筛选"
                value={query.status}
                disabled={busy}
                options={FILTERS.map((filter) => ({
                  value: filter.value,
                  label: filter.label,
                  count: counts ? filter.count(counts) : undefined,
                }))}
                onChange={setStatus}
              />
              <Button variant="primary" disabled={busy} onClick={() => setImporting(true)}>
                导入海关回执
              </Button>
            </div>
          }
        />
        <CustomsSearchForm
          busy={busy}
          initial={EMPTY_CUSTOMS_SEARCH}
          onSearch={(criteria) => setQuery((current) => ({ ...current, ...criteria, page: 1 }))}
        />
        <div className="fr-preview">
          {state.kind === "ready" && (
            <ReviewListToolbar
              summary={
                <>
                  本页 {items.length} 张海关回执
                  {batch && (
                    <>
                      {" "}
                      · 已勾选 <b>{chosen.length}</b> 张（本页可审核 {selectable.length} 张）
                    </>
                  )}
                </>
              }
            >
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => setExpanded(items.map((item) => item.id))}
              >
                全部展开
              </Button>
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => setExpanded([])}>
                全部收起
              </Button>
              <Button size="sm" disabled={busy} onClick={reload}>
                刷新列表
              </Button>
              {batch ? (
                <>
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      setBatch(false);
                      setSelection([]);
                    }}
                  >
                    取消批量
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={busy || !chosen.length}
                    onClick={() => setApproval(chosen)}
                  >
                    确认审核通过（{chosen.length}）
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy || !selectable.length}
                  title={!selectable.length ? "本页没有可审核的海关回执" : undefined}
                  onClick={() => {
                    setBatch(true);
                    setSelection([]);
                  }}
                >
                  批量审核通过
                </Button>
              )}
            </ReviewListToolbar>
          )}
          <ReceiptList
            state={state}
            busy={busy}
            expanded={expanded}
            onToggle={(id) =>
              setExpanded((current) =>
                current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
              )
            }
            onRetry={reload}
            onImport={() => setImporting(true)}
            batch={batch}
            selection={selection}
            onSelect={(id, checked) =>
              setSelection((current) =>
                checked ? [...current, id] : current.filter((value) => value !== id),
              )
            }
            onSelectAll={(checked) => setSelection(checked ? selectable.map((item) => item.id) : [])}
            onApprove={(item) => setApproval([item])}
          />
          {state.kind === "ready" && state.result.total > 0 && (
            <CardFooter>
              <Pagination
                label="海关回执分页"
                unit="张"
                total={state.result.total}
                page={state.result.page}
                pageCount={state.result.pages}
                pageSize={state.result.pageSize}
                pageSizes={[10, 20, 50]}
                disabled={busy}
                onPageChange={(page) => setQuery((current) => ({ ...current, page }))}
                onPageSizeChange={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))}
              />
            </CardFooter>
          )}
        </div>
      </Card>
      {importing && (
        <CustomsImportDialog
          onClose={(changed) => {
            setImporting(false);
            if (changed) reload();
          }}
        />
      )}
      {approval && (
        <CustomsApproveDialog
          items={approval}
          onChanged={() => {
            setSelection([]);
            reload();
          }}
          onClose={() => setApproval(null)}
        />
      )}
    </div>
  );
}

function ReceiptList({
  state,
  busy,
  expanded,
  onToggle,
  onRetry,
  onImport,
  batch,
  selection,
  onSelect,
  onSelectAll,
  onApprove,
}: {
  state: ListState;
  busy: boolean;
  expanded: number[];
  onToggle: (id: number) => void;
  onRetry: () => void;
  onImport: () => void;
  batch: boolean;
  selection: number[];
  onSelect: (id: number, checked: boolean) => void;
  onSelectAll: (checked: boolean) => void;
  onApprove: (item: CustomsReceipt) => void;
}) {
  if (state.kind === "loading") return <Skeleton label="正在读取海关回执与比对结果" />;
  if (state.kind === "error")
    return (
      <ErrorState
        title="海关回执暂时无法加载"
        message={state.message}
        action={<Button onClick={onRetry}>重新查询</Button>}
      />
    );
  const { result } = state;
  if (!result.items.length)
    return result.counts.receipts === 0 ? (
      <EmptyState
        title="还没有导入海关回执"
        description="导入单一窗口导出的报关单明细后，系统按出口报关单号自动比对 NS 报关单。"
        action={
          <Button variant="primary" onClick={onImport}>
            导入海关回执
          </Button>
        }
      />
    ) : (
      <EmptyState title="没有符合条件的海关回执" description="请调整查询条件或比对结果筛选。" />
    );
  const selectable = result.items.filter((item) => item.approval.allowed);
  const allChosen = selectable.length > 0 && selectable.every((item) => selection.includes(item.id));
  return (
    <div
      className="fr-declaration-scroll"
      role="region"
      aria-label="海关回执列表，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 原生宽表区域需支持键盘聚焦及横向滚动。
      tabIndex={0}
    >
      <table className="fr-declaration-table">
        <caption className="fr-sr-only">海关回执主行，展开查看 NS 报关行与海关项的明细比对</caption>
        <colgroup>
          {(batch ? BATCH_WIDTHS : COLUMN_WIDTHS).map((width, index) => (
            <col key={index} style={{ width: `${width}%` }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {batch && (
              <th scope="col" className="fr-check-cell">
                {selectable.length > 0 && (
                  <input
                    type="checkbox"
                    checked={allChosen}
                    aria-label="选择当前页全部可审核的海关回执"
                    disabled={busy}
                    onChange={(event) => onSelectAll(event.target.checked)}
                  />
                )}
              </th>
            )}
            <th scope="col" className="fr-toggle-heading">
              出口报关单号
            </th>
            <th scope="col">出口日期</th>
            <th scope="col">征免</th>
            <th scope="col">明细行</th>
            <th scope="col">境外收货人（海关回执）</th>
            <th scope="col">明细比对</th>
            <th scope="col">海关审核</th>
            <th scope="col" className="fr-declaration-action">
              操作
            </th>
          </tr>
        </thead>
        {result.items.map((receipt) => (
          <CustomsReceiptRow
            key={receipt.id}
            receipt={receipt}
            open={expanded.includes(receipt.id)}
            busy={busy}
            onToggle={() => onToggle(receipt.id)}
            batch={batch}
            selected={selection.includes(receipt.id)}
            onSelect={(checked) => onSelect(receipt.id, checked)}
            onApprove={() => onApprove(receipt)}
          />
        ))}
      </table>
    </div>
  );
}
