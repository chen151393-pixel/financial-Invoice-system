import { ConversionFields, defaultConversion } from "./ConversionFields";
import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { tierLabels, type Candidate, type InvoiceItem, type ManualBody } from "../types/matching";
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
}: {
  invoiceId: string;
  invoiceVersionId: string | null;
  item: InvoiceItem;
  busy: boolean;
  search: (keyword: string) => Promise<{ rows: Candidate[]; total: number }>;
  replacements: { id: string; label: string }[];
  onCreate: (body: ManualBody, replaceId: string, reason: string) => Promise<boolean>;
}) {
  const [replaceId, setReplaceId] = useState("");
  const [reason, setReason] = useState("");
  const [conversion, setConversion] = useState(defaultConversion);
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState<Search>({ kind: "idle" });
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
      {replacements.length > 0 && (
        <label>
          分配方式
          <select
            value={replaceId}
            disabled={busy}
            onChange={(e) => {
              setReplaceId(e.target.value);
              setRequestId(crypto.randomUUID());
            }}
          >
            <option value="">新增分配</option>
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
          替换原因（新分配失败时原占用保持不变）
          <textarea
            value={reason}
            maxLength={300}
            disabled={busy}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
      )}
      <p className="matching-help">
        从已审核的应开范围中选择子采购行，按实际开票填写本次分配的数量与含税金额；保存后直接通过并更新任务收票进度。
      </p>
      <form
        className="matching-row"
        onSubmit={(event) => {
          event.preventDefault();
          void find();
        }}
      >
        <input
          aria-label="按子采购单号、供应商、品名或报关单号查询"
          placeholder="子采购单号 / 供应商 / 品名 / 报关单号"
          maxLength={100}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Button type="submit" disabled={state.kind === "loading"}>
          查询候选
        </Button>
      </form>
      {state.kind === "loading" && <p role="status">正在查询…</p>}
      {state.kind === "error" && (
        <p role="alert" className="matching-feedback">
          {state.message}
        </p>
      )}
      {state.kind === "ready" && state.rows.length === 0 && (
        <p className="matching-empty">没有符合条件的未结束子采购行。</p>
      )}
      {state.kind === "ready" &&
        state.rows.map((candidate) => (
          <label key={candidate.purchase.purchaseLineId} className="matching-check">
            <input
              type="radio"
              name={`candidate-${item.id}`}
              checked={chosen?.purchase.purchaseLineId === candidate.purchase.purchaseLineId}
              onChange={() => {
                setChosen(candidate);
                setRequestId(crypto.randomUUID());
              }}
            />
            {candidate.purchase.orderNo} · {candidate.purchase.item} · 剩余{" "}
            {candidate.purchase.remainingQuantity ?? "—"} / {candidate.purchase.remainingAmount ?? "—"} ·
            置信度 {candidate.confidence}（{tierLabels[candidate.tier]}）
            {candidate.block && <span className="matching-warning"> · {candidate.block}</span>}
          </label>
        ))}
      {state.kind === "ready" && state.total > state.rows.length && (
        <p className="matching-help">
          共 {state.total} 条，仅显示置信度最高的 {state.rows.length} 条，请输入关键字缩小范围。
        </p>
      )}
      {replaceId && (
        <p className="matching-help">候选显示替换前的剩余应开。提交时会先扣除原分配，再核算新分配。</p>
      )}
      {chosen && (
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
          <ChecksTable checks={chosen.checks} caption="与所选子采购行逐项比对" />
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
            {busy ? "保存中…" : replaceId ? "替换并通过" : "保存并通过"}
          </Button>
        </form>
      )}
    </div>
  );
}
