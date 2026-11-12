import { useEffect, useRef, useState } from "react";
import {
  Alert,
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
import { CustomsImportDialog } from "../components/CustomsImportDialog";
import { CustomsReceiptRow } from "../components/CustomsReceiptRow";
import { CustomsSearchForm, EMPTY_CUSTOMS_SEARCH } from "../components/CustomsSearchForm";
import { CustomsStats } from "../components/CustomsStats";
import { queryCustomsReceipts, rematchCustomsReceipts } from "../customs-api";
import type { CustomsCounts, CustomsFilter, CustomsReceiptList, CustomsReceiptQuery } from "../customs-types";
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

/** 海关报关单比对：导入海关回执，按真实报关单号与 NS 报关单比对明细，并保存回执中的境外收货人。 */
export function CustomsMatchPage() {
  const [query, setQuery] = useState<CustomsReceiptQuery>({
    ...EMPTY_CUSTOMS_SEARCH,
    status: "all",
    page: 1,
    pageSize: 20,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  // 最近一次成功的计数：重新查询时保留，概况卡与状态切换不闪烁
  const [counts, setCounts] = useState<CustomsCounts | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [expanded, setExpanded] = useState<number[]>([]);
  const [importing, setImporting] = useState(false);
  const [rematching, setRematching] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const rematchLock = useRef(false);

  useEffect(() => {
    // 条件快速切换时取消旧请求，旧响应不覆盖新结果
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryCustomsReceipts(query, controller.signal);
        setState({ kind: "ready", result });
        setCounts(result.counts);
        // 默认展开有差异的报关单，便于直接查看
        setExpanded(result.items.filter((item) => item.status === "different").map((item) => item.id));
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  async function rematch(ids: number[]) {
    if (rematchLock.current) return;
    rematchLock.current = true;
    setRematching(true);
    setNotice(null);
    try {
      const result = await rematchCustomsReceipts(ids);
      setNotice({ tone: "success", text: `已按当前 NS 报关单重新匹配 ${result.rematched} 张海关回执` });
    } catch (error) {
      setNotice({
        tone: "danger",
        text: error instanceof Error ? error.message : "重新匹配失败，请稍后重试",
      });
    } finally {
      rematchLock.current = false;
      setRematching(false);
      setRefresh((value) => value + 1);
    }
  }

  // 打开导入时清除上一次重新匹配的提示，避免与导入结果混淆
  const openImport = () => {
    setNotice(null);
    setImporting(true);
  };
  const busy = state.kind === "loading" || rematching;
  const setStatus = (status: CustomsFilter) => setQuery((current) => ({ ...current, status, page: 1 }));
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
              <Button disabled={busy || !counts?.receipts} onClick={() => void rematch([])}>
                {rematching ? "匹配中…" : "全部重新匹配"}
              </Button>
              <Button variant="primary" disabled={rematching} onClick={openImport}>
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
        <details className="cm-rules">
          <summary>比对口径</summary>
          <ol>
            <li>以海关“出口报关单号”对应 NS 报关单的真实报关单号（不是 CD 号）。</li>
            <li>
              同一报关单内按“海关商品名称 + 成交单位”归组，合计成交数量后与 NS 报关行数量精确比较；NS
              一行可对应海关多项（拆行），多行也可对应一项（合并）。
            </li>
            <li>单位按海关“成交单位”与 NS 报关单位比较；法定单位与法定数量只展示，不参与判定。</li>
            <li>
              境外收货人只来自海关回执（NS
              报关单没有该字段），不参与比对；报关单号匹配后随报关单保存，未匹配的回执找到 NS 报关单后再关联。
            </li>
          </ol>
        </details>
        <div role="status" aria-live="polite" className="cm-notice">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        </div>
        <ReceiptList
          state={state}
          busy={busy}
          expanded={expanded}
          onToggle={(id) =>
            setExpanded((current) =>
              current.includes(id) ? current.filter((v) => v !== id) : [...current, id],
            )
          }
          onRematch={(id) => void rematch([id])}
          onRetry={() => setRefresh((value) => value + 1)}
          onImport={openImport}
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
      </Card>
      {importing && (
        <CustomsImportDialog
          onClose={(changed) => {
            setImporting(false);
            if (changed) setRefresh((value) => value + 1);
          }}
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
  onRematch,
  onRetry,
  onImport,
}: {
  state: ListState;
  busy: boolean;
  expanded: number[];
  onToggle: (id: number) => void;
  onRematch: (id: number) => void;
  onRetry: () => void;
  onImport: () => void;
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
  return (
    <div
      className="fr-declaration-scroll"
      role="region"
      aria-label="海关回执列表，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 原生宽表区域需支持键盘聚焦及横向滚动。
      tabIndex={0}
    >
      <table className="fr-declaration-table cm-table">
        <caption className="fr-sr-only">海关回执主行，展开查看 NS 报关行与海关项的明细比对</caption>
        <colgroup>
          <col style={{ width: "19%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "6%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "22%" }} />
          <col style={{ width: "21%" }} />
          <col style={{ width: "10%" }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="fr-toggle-heading">
              出口报关单号
            </th>
            <th scope="col">出口日期</th>
            <th scope="col">征免</th>
            <th scope="col">明细行</th>
            <th scope="col">境外收货人（海关回执）</th>
            <th scope="col">明细比对</th>
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
            onRematch={() => onRematch(receipt.id)}
          />
        ))}
      </table>
    </div>
  );
}
