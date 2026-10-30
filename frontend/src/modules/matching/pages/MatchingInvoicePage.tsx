import { useEffect, useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Alert, Button, Card, EmptyState, ErrorState, Skeleton } from "../../../shared/components/ui";
import { openLocalSession } from "../../identity/api";
import {
  cancelAllocation,
  confirmAllocation,
  confirmGroup,
  createManualOrder,
  findManualOrders,
  generateProposals,
  getInvoiceMatching,
  rejectAllocation,
  rejectGroup,
  reverifyAllocation,
} from "../api";
import { groupAllocations } from "../components/allocation-groups";
import { InvoiceLineNav } from "../components/InvoiceLineNav";
import { InvoiceLinePanel } from "../components/InvoiceLinePanel";
import { InvoicePaper } from "../components/InvoicePaper";
import type { InvoiceMatching } from "../types/matching";
import "./matching.css";
import "./matching-parts.css";
import "../components/matching-detail.css";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  if (state.kind === "loading") return <Skeleton label="正在读取发票比对" rows={4} />;
  if (state.kind === "error")
    return (
      <ErrorState
        title="发票比对暂时无法加载"
        message={state.message}
        action={
          <>
            <Button
              onClick={() => {
                setState({ kind: "loading" });
                setRefresh((value) => value + 1);
              }}
            >
              重新加载
            </Button>
            <Link to={paths.matching}>返回审核队列</Link>
          </>
        }
      />
    );
  const { invoice, items, generate, groups } = state.data;
  // 默认选中第一条有待处理事项的发票行，否则选第一行；仅是展示选择，不改变业务数据。
  const selected =
    items.find((item) => item.id === selectedId) ??
    items.find((item) => groups.some((group) => group.items.some((row) => row.invoiceItemId === item.id))) ??
    items.find((item) => groupAllocations(item.allocations).pending.length > 0) ??
    items[0];
  const replacements = items.flatMap((row) =>
    row.allocations
      .filter((a) => a.replace.allowed)
      .map((a) => ({ id: a.id, label: `${a.purchase?.orderNo ?? ""} · ${a.amount}` })),
  );
  return (
    <div className="matching-page">
      <InvoicePaper
        value={state.data}
        selectedId={selected?.id ?? null}
        actions={
          <Button
            disabled={busy || !generate.allowed}
            title={generate.reason}
            onClick={() => void regenerate()}
          >
            重新生成建议
          </Button>
        }
      />
      {!generate.allowed && <Alert tone="warning">{generate.reason}</Alert>}
      {feedback && <Alert tone={feedback.error ? "danger" : "success"}>{feedback.text}</Alert>}
      {selected ? (
        <div className="matching-detail">
          <InvoiceLineNav
            items={items}
            groups={groups}
            selectedId={selected.id}
            onSelect={setSelectedId}
            busy={busy}
          />
          <InvoiceLinePanel
            key={selected.id}
            item={selected}
            invoice={invoice}
            groups={groups}
            invoiceId={invoiceId}
            linkedGroups={state.data.linkedGroups}
            invoiceVersionId={invoice.versionId}
            replacements={replacements}
            busy={busy}
            actions={{
              confirm: (id, body) =>
                void act(() => confirmAllocation(id, body), "已通过，任务收票进度已更新。"),
              reverify: (id, body) =>
                void act(() => reverifyAllocation(id, body), "已重新核实，任务收票进度已更新。"),
              reject: (id, note) => void act(() => rejectAllocation(id, note), "已驳回该建议。"),
              cancel: (id, reason) =>
                act(() => cancelAllocation(id, reason), "已删除关联，任务收票进度已回退。"),
              create: (body) =>
                act(
                  () => createManualOrder(body),
                  body.replaceAllocationId
                    ? "已替换原关联，整单关联已通过。"
                    : "整单关联已保存并通过，任务收票进度已更新。",
                ),
              search: (keyword) => findManualOrders(invoiceId, selected.id, keyword),
              confirmGroup: (groupId, note) =>
                act(
                  () => confirmGroup(groupId, invoiceId, invoice.versionId, note),
                  "整单已通过，全部子采购明细已记入收票进度。",
                ),
              rejectGroup: (groupId, note) =>
                act(() => rejectGroup(groupId, invoiceId, note), "已驳回整单建议。"),
            }}
          />
        </div>
      ) : (
        <Card>
          <EmptyState title="这张发票没有可比对的明细" description="请先在进项发票中补齐商品明细。" />
        </Card>
      )}
    </div>
  );
}
