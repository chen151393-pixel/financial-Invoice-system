import { useEffect, useRef, useState } from "react";
import { Button, EmptyState, ErrorState, Skeleton } from "../../../shared/components/ui";
import type { InvoiceItem } from "../types/matching";
import type { ManualOrderBody, ManualOrderCandidate, ManualOrderCandidates } from "../types/manual-order";
import { CandidateTable } from "./CandidateTable";
import { OrderShareForm } from "./OrderShareForm";

type Search =
  | { kind: "idle" | "loading" }
  | { kind: "error"; message: string }
  | ({ kind: "ready" } & ManualOrderCandidates);

/** 手动关联：查询整张子采购单候选，选中后展开该单明细逐行填写本票分配。 */
export function ManualAllocation({
  invoiceId,
  invoiceVersionId,
  item,
  busy,
  search,
  onCreate,
  replacements,
  showForm = true,
  onShowForm,
}: {
  invoiceId: string;
  invoiceVersionId: string | null;
  item: InvoiceItem;
  busy: boolean;
  search: (keyword: string) => Promise<ManualOrderCandidates>;
  replacements: { id: string; label: string }[];
  onCreate: (body: ManualOrderBody) => Promise<boolean>;
  showForm?: boolean;
  onShowForm?: () => void;
}) {
  const [replaceId, setReplaceId] = useState("");
  const [reason, setReason] = useState("");
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState<Search>({ kind: "loading" });
  const [chosen, setChosen] = useState<ManualOrderCandidate | null>(null);
  const initialSearch = useRef(search);
  useEffect(() => {
    let active = true;
    void initialSearch
      .current("")
      .then((result) => {
        if (active) setState({ kind: "ready", ...result });
      })
      .catch((error: unknown) => {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "候选查询失败" });
      });
    return () => {
      active = false;
    };
  }, []);

  async function find() {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", ...(await search(keyword)) });
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "候选查询失败" });
    }
  }
  return (
    <div className="matching-form">
      {showForm && replacements.length > 0 && (
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
        className="matching-row"
        onSubmit={(event) => {
          event.preventDefault();
          void find();
        }}
      >
        <label>
          查询子采购单
          <input
            aria-label="按子采购单号、母采购单号、供应商、品名或报关单号查询"
            placeholder="子采购单号 / 母采购单号 / 供应商 / 品名 / 报关单号"
            maxLength={100}
            value={keyword}
            disabled={busy || state.kind === "loading"}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </label>
        <Button type="submit" disabled={busy || state.kind === "loading"}>
          查询候选
        </Button>
      </form>
      {state.kind === "loading" && <Skeleton label="正在查询候选子采购单" rows={2} />}
      {state.kind === "error" && (
        <ErrorState
          title="候选查询失败"
          message={state.message}
          action={<Button onClick={() => void find()}>重新查询</Button>}
        />
      )}
      {state.kind === "ready" && !state.rows.length && (
        <EmptyState title="没有符合条件的子采购单" description="可以修改关键字后重新查询。" />
      )}
      {state.kind === "ready" && state.rows.length > 0 && (
        <CandidateTable
          rows={state.rows}
          busy={busy}
          chosenId={chosen?.purchaseOrderId ?? null}
          onChoose={(candidate) => {
            setChosen(candidate);
            onShowForm?.();
          }}
        />
      )}
      {state.kind === "ready" && state.total > state.rows.length && (
        <p className="matching-help">
          共 {state.total} 张，仅显示置信度最高的 {state.rows.length} 张，请输入关键字缩小范围。
        </p>
      )}
      {chosen && showForm && (
        <OrderShareForm
          key={`${chosen.purchaseOrderId}:${replaceId}`}
          order={chosen}
          item={item}
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
    </div>
  );
}
