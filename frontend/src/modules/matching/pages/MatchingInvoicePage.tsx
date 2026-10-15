import { useEffect, useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { openLocalSession } from "../../identity/api";
import {
  cancelAllocation,
  confirmAllocation,
  createAllocation,
  findCandidates,
  generateProposals,
  getInvoiceMatching,
  rejectAllocation,
} from "../api";
import { AllocationCard } from "../components/AllocationCard";
import { ManualAllocation } from "../components/ManualAllocation";
import type { InvoiceMatching, ManualBody } from "../types/matching";
import "./matching.css";

type Remote =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: InvoiceMatching };
type Feedback = { error: boolean; text: string } | null;

export function MatchingInvoicePage({ invoiceId }: { invoiceId: string }) {
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [manualItem, setManualItem] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getInvoiceMatching(invoiceId);
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "比对读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [invoiceId, refresh]);

  // 写操作的结果以后端返回的比对视图为准；失败显示真实原因，不自动重试。
  async function act(action: () => Promise<InvoiceMatching>, done: string) {
    if (busy) return false;
    setBusy(true);
    setFeedback(null);
    try {
      setState({ kind: "ready", data: await action() });
      setFeedback({ error: false, text: done });
      return true;
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "操作失败，请刷新后核对" });
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function regenerate() {
    setBusy(true);
    setFeedback(null);
    try {
      const result = await generateProposals([invoiceId]);
      setFeedback({ error: false, text: `已生成 ${result.created} 条新建议。` });
      setRefresh((value) => value + 1);
    } catch (error) {
      setFeedback({ error: true, text: error instanceof Error ? error.message : "生成失败" });
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading")
    return (
      <p role="status" className="matching-panel">
        正在读取发票比对…
      </p>
    );
  if (state.kind === "error")
    return (
      <div className="matching-panel" role="alert">
        <p>{state.message}</p>
        <Button
          onClick={() => {
            setState({ kind: "loading" });
            setRefresh((value) => value + 1);
          }}
        >
          重新加载
        </Button>
        <Link to={paths.matching}>返回审核队列</Link>
      </div>
    );
  const { invoice, items, generate } = state.data;
  return (
    <div className="matching-page">
      <section className="matching-panel" aria-label="发票信息">
        <div className="matching-heading">
          <h2>发票 {invoice.number}</h2>
          <div className="matching-row">
            <Button
              disabled={busy || !generate.allowed}
              title={generate.reason}
              onClick={() => void regenerate()}
            >
              重新生成建议
            </Button>
            <Link to={paths.matching}>返回审核队列</Link>
          </div>
        </div>
        <dl className="matching-facts">
          {[
            ["销售方", invoice.seller],
            ["购买方", invoice.buyer ?? "导入文件未提供"],
            ["开票日期", invoice.date],
            ["价税合计", `${invoice.gross ?? "—"} ${invoice.currency}`],
            ["票面状态", invoice.statusLabel],
            ["备注", invoice.remark],
          ].map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || "—"}</dd>
            </div>
          ))}
        </dl>
        <p className="matching-help">
          {generate.reason}。全部建议需人工审核；通过后自动更新开票任务的收票进度。
        </p>
        {feedback && (
          <p className="matching-feedback" role={feedback.error ? "alert" : "status"}>
            {feedback.text}
          </p>
        )}
      </section>
      <section className="matching-panel" aria-label="发票行比对">
        <h2>发票行（{items.length}）</h2>
        {items.map((item) => (
          <div key={item.id} className="matching-item">
            <div className="matching-heading">
              <h3>
                {item.lineNo}. {item.item ?? "—"} {item.specification && `· ${item.specification}`}
              </h3>
              <span>
                {item.quantity ?? "—"} {item.unit ?? ""} · 含税 {item.amount ?? "—"} · 已通过{" "}
                {item.confirmedQuantity} / {item.confirmedAmount}
              </span>
            </div>
            {item.allocations.length === 0 && (
              <p className="matching-help">暂无建议：没有可召回的已审核子采购行。</p>
            )}
            {item.allocations.map((allocation) => (
              <AllocationCard
                key={`${allocation.id}:${allocation.status}`}
                allocation={allocation}
                busy={busy}
                onConfirm={(body) =>
                  void act(() => confirmAllocation(allocation.id, body), "已通过，任务收票进度已更新。")
                }
                onReject={(note) => void act(() => rejectAllocation(allocation.id, note), "已驳回该建议。")}
                onCancel={(reason) =>
                  void act(() => cancelAllocation(allocation.id, reason), "已取消分配，任务收票进度已回退。")
                }
              />
            ))}
            <Button disabled={busy} onClick={() => setManualItem(manualItem === item.id ? null : item.id)}>
              {manualItem === item.id ? "收起人工分配" : "人工分配到其他子采购行"}
            </Button>
            {manualItem === item.id && (
              <ManualAllocation
                invoiceId={invoiceId}
                item={item}
                busy={busy}
                search={(keyword) => findCandidates(invoiceId, item.id, keyword)}
                onCreate={(body: ManualBody) => act(() => createAllocation(body), "人工分配已保存并通过。")}
              />
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
