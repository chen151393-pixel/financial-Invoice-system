import { useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import type { InvoiceItem, InvoiceMatching } from "../types/matching";
import type { ManualOrderBody, ManualOrderCandidate, ManualOrderCandidates } from "../types/manual-order";
import { CandidateTable } from "./CandidateTable";
import { OrderShareForm, type OrderOrigin } from "./OrderShareForm";

type Search =
  | { kind: "idle" | "loading" }
  | { kind: "error"; message: string }
  // 不带关键字：后端只返回置信度最高的一张（可能为空），total 为全部候选张数
  | { kind: "default"; total: number }
  | ({ kind: "results" } & ManualOrderCandidates);

type Chosen = { order: ManualOrderCandidate; origin: OrderOrigin; total: number };

const errorText = (error: unknown) => (error instanceof Error ? error.message : "候选查询失败");
// 空关键字返回默认候选：有则直接选中，作为“置信度最高”展示
const bestOf = (result: ManualOrderCandidates): Chosen | null =>
  result.rows[0] ? { order: result.rows[0], origin: "best", total: result.total } : null;

/**
 * 手动关联整张子采购单。autoLoad 时（本行没有建议和已关联）打开即展示置信度最高的候选及其整单比对；
 * 不是这张时按单号查询改选。否则收起，点“手动关联”后再查询。候选、比对与限制均来自后端。
 */
export function ManualAllocation({
  invoiceId,
  invoiceVersionId,
  item,
  invoice,
  busy,
  search,
  onCreate,
  replacements,
  autoLoad,
}: {
  invoiceId: string;
  invoiceVersionId: string | null;
  item: InvoiceItem;
  invoice: InvoiceMatching["invoice"];
  busy: boolean;
  search: (keyword: string) => Promise<ManualOrderCandidates>;
  replacements: { id: string; label: string }[];
  onCreate: (body: ManualOrderBody) => Promise<boolean>;
  autoLoad: boolean;
}) {
  const [open, setOpen] = useState(autoLoad);
  const [replaceId, setReplaceId] = useState("");
  const [reason, setReason] = useState("");
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState<Search>(autoLoad ? { kind: "loading" } : { kind: "idle" });
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const initialSearch = useRef(search);

  useEffect(() => {
    if (!autoLoad) return;
    let active = true;
    void initialSearch
      .current("")
      .then((result) => {
        if (!active) return;
        setChosen(bestOf(result));
        setState({ kind: "default", total: result.total });
      })
      .catch((error: unknown) => {
        if (active) setState({ kind: "error", message: errorText(error) });
      });
    return () => {
      active = false;
    };
  }, [autoLoad]);

  async function find() {
    const text = keyword.trim();
    setState({ kind: "loading" });
    try {
      const result = await search(text);
      if (text) {
        setState({ kind: "results", ...result });
        return;
      }
      setChosen(bestOf(result));
      setState({ kind: "default", total: result.total });
    } catch (error) {
      setState({ kind: "error", message: errorText(error) });
    }
  }

  const loading = state.kind === "loading";
  // 查询结果列表、加载或失败时先隐藏比对卡，避免把旧候选误当成当前选择
  const current = ["results", "loading", "error"].includes(state.kind) ? null : chosen;
  return (
    <>
      <Card aria-label="关联整张子采购单">
        <CardHeader
          title={`第 ${item.lineNo || "—"} 行 · 关联整张子采购单`}
          description={
            autoLoad ? (
              <span className="matching-row">
                <Badge tone="neutral">没有待审核建议</Badge>
                <span>
                  没有系统建议时在此关联整张子采购单。一张子采购单只能由一张发票开具，发票少开的差额在关联后按差异结束。
                </span>
              </span>
            ) : (
              "以整张子采购单为最小关联单位，按单号查询后选择。已有待审核建议时请先驳回；已通过的关联可选择替换。"
            )
          }
          actions={
            !autoLoad && (
              <Button disabled={busy} aria-expanded={open} onClick={() => setOpen(!open)}>
                {open ? "收起手动关联" : "手动关联"}
              </Button>
            )
          }
        />
        {open && (
          <CardContent className="matching-form">
            {replacements.length > 0 && (
              <label>
                关联方式
                <select value={replaceId} disabled={busy} onChange={(e) => setReplaceId(e.target.value)}>
                  <option value="">新增关联</option>
                  {replacements.map((row) => (
                    <option key={row.id} value={row.id}>
                      替换记录 {row.id} · {row.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {replaceId && (
              <label>
                替换原因（候选显示替换前的剩余应开；新关联失败时原占用保持不变）
                <textarea
                  value={reason}
                  maxLength={300}
                  disabled={busy}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
            )}
            <form
              className="matching-row matching-order-search"
              onSubmit={(event) => {
                event.preventDefault();
                void find();
              }}
            >
              <label>
                {autoLoad ? "按单号改选" : "查询子采购单"}
                <input
                  type="search"
                  aria-label="按子采购单号、母采购单号、供应商、品名或报关单号查询"
                  placeholder="子采购单号 / 母采购单号 / 供应商 / 品名 / 报关单号，至少 3 个字符"
                  maxLength={100}
                  value={keyword}
                  disabled={busy || loading}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </label>
              <Button type="submit" disabled={busy || loading}>
                查询
              </Button>
            </form>
            {loading && <Skeleton label="正在查询候选子采购单" rows={2} />}
            {state.kind === "error" && (
              <ErrorState
                title="候选查询失败"
                message={state.message}
                action={<Button onClick={() => void find()}>重新查询</Button>}
              />
            )}
            {current && (
              <p className="matching-help" role="status">
                {current.origin === "best"
                  ? `下方默认展示置信度最高的候选 ${current.order.orderNo}（共 ${current.total} 张候选），不是这张可按单号改选。`
                  : `下方为手动选择的 ${current.order.orderNo}，可继续按单号改选；清空关键字查询可回到置信度最高的候选。`}
              </p>
            )}
            {state.kind === "default" && !chosen && (
              <EmptyState
                title="没有可默认展示的候选"
                description={
                  state.total
                    ? `共 ${state.total} 张候选，但没有与本发票行相符且可关联的子采购单，请输入单号查询。`
                    : "没有可关联的子采购单（须开票依据已审核且尚未由其他发票开具），请确认后再查询。"
                }
              />
            )}
            {state.kind === "results" && !state.rows.length && (
              <EmptyState title="没有符合条件的子采购单" description="可以修改单号后重新查询。" />
            )}
            {state.kind === "results" && state.rows.length > 0 && (
              <CandidateTable
                rows={state.rows}
                busy={busy}
                chosenId={chosen?.order.purchaseOrderId ?? null}
                onChoose={(candidate) => {
                  setChosen({ order: candidate, origin: "picked", total: state.total });
                  setState({ kind: "idle" });
                }}
              />
            )}
            {state.kind === "results" && state.total > state.rows.length && (
              <p className="matching-help">
                共 {state.total} 张，仅显示置信度最高的 {state.rows.length} 张，请输入更完整的单号。
              </p>
            )}
          </CardContent>
        )}
      </Card>
      {open && current && (
        <OrderShareForm
          key={`${current.order.purchaseOrderId}:${current.origin}:${replaceId}`}
          order={current.order}
          origin={current.origin}
          item={item}
          invoice={invoice}
          invoiceId={invoiceId}
          invoiceVersionId={invoiceVersionId}
          replaceId={replaceId}
          reason={reason}
          busy={busy}
          onCreate={(body) =>
            onCreate(body).then((saved) => {
              if (saved) {
                setChosen(null);
                setReplaceId("");
                setReason("");
                setState({ kind: "idle" });
              }
              return saved;
            })
          }
        />
      )}
    </>
  );
}
