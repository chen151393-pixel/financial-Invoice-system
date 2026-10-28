import { ConversionFields, defaultConversion } from "./ConversionFields";
import { useEffect, useRef, useState } from "react";
import { Button, EmptyState, ErrorState, Skeleton } from "../../../shared/components/ui";
import type { Candidate, InvoiceItem, ManualBody } from "../types/matching";
import { CandidateTable } from "./CandidateTable";
import { ChecksTable } from "./ChecksTable";

type Search =
  | { kind: "idle" | "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; rows: Candidate[]; total: number };

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
  search: (keyword: string) => Promise<{ rows: Candidate[]; total: number }>;
  replacements: { id: string; label: string }[];
  onCreate: (body: ManualBody, replaceId: string, reason: string) => Promise<boolean>;
  showForm?: boolean;
  onShowForm?: () => void;
}) {
  const [replaceId, setReplaceId] = useState("");
  const [reason, setReason] = useState("");
  const [conversion, setConversion] = useState(defaultConversion);
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState<Search>({ kind: "loading" });
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
  const [chosen, setChosen] = useState<Candidate | null>(null);
  const [form, setForm] = useState({
    quantity: item.quantity ?? "",
    amount: item.amount ?? "",
    note: "",
  });
  // 同一次填写沿用同一请求标识：提交结果不明时重试不会重复分配。
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());

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
          <select
            value={replaceId}
            disabled={busy}
            onChange={(e) => {
              setReplaceId(e.target.value);
              setRequestId(crypto.randomUUID());
            }}
          >
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
          替换原因（候选显示替换前的剩余应开；新分配失败时原占用保持不变）
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
          查询子采购行
          <input
            aria-label="按子采购单号、供应商、品名或报关单号查询"
            placeholder="子采购单号 / 供应商 / 品名 / 报关单号"
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
      {state.kind === "loading" && <Skeleton label="正在查询候选子采购行" rows={2} />}
      {state.kind === "error" && (
        <ErrorState
          title="候选查询失败"
          message={state.message}
          action={<Button onClick={() => void find()}>重新查询</Button>}
        />
      )}
      {state.kind === "ready" && !state.rows.length && (
        <EmptyState title="没有符合条件的子采购行" description="可以修改关键字后重新查询。" />
      )}
      {state.kind === "ready" && state.rows.length > 0 && (
        <CandidateTable
          rows={state.rows}
          busy={busy}
          name={`candidate-${item.id}`}
          chosenId={chosen?.purchase.purchaseLineId ?? null}
          onChoose={(candidate) => {
            setChosen(candidate);
            onShowForm?.();
            setRequestId(crypto.randomUUID());
          }}
        />
      )}
      {state.kind === "ready" && state.total > state.rows.length && (
        <p className="matching-help">
          共 {state.total} 条，仅显示置信度最高的 {state.rows.length} 条，请输入关键字缩小范围。
        </p>
      )}
      {chosen && showForm && (
        <form
          className="matching-form"
          onSubmit={(event) => {
            event.preventDefault();
            void onCreate(
              {
                requestId,
                invoiceId,
                invoiceItemId: item.id,
                purchaseLineId: chosen.purchase.purchaseLineId,
                quantity: form.quantity,
                amount: form.amount,
                note: form.note,
                ...conversion,
                invoiceVersionId,
                purchaseBasisId: chosen.purchase.purchaseBasisId,
              },
              replaceId,
              reason,
            ).then((saved) => {
              if (!saved) return;
              setChosen(null);
              setReplaceId("");
              setReason("");
              setRequestId(crypto.randomUUID());
              setState({ kind: "idle" });
            });
          }}
        >
          <details open>
            <summary>与所选子采购行逐项比对</summary>
            <ChecksTable checks={chosen.checks} caption="与所选子采购行逐项比对" />
          </details>
          <div className="matching-row">
            <label>
              分配数量
              <input
                value={form.quantity}
                disabled={busy}
                onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              />
            </label>
            <label>
              分配含税金额
              <input
                value={form.amount}
                disabled={busy}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </label>
          </div>
          <ConversionFields value={conversion} onChange={setConversion} busy={busy} />
          <label>
            审核说明（有不一致项或超开时必填）
            <textarea
              rows={2}
              maxLength={300}
              value={form.note}
              disabled={busy}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          <Button type="submit" variant="primary" disabled={busy || !!chosen.block}>
            {busy ? "保存中…" : replaceId ? "替换并通过" : "保存关联并通过"}
          </Button>
        </form>
      )}
    </div>
  );
}
