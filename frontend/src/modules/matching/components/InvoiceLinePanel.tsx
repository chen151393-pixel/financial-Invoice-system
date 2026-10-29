import { useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, EmptyState } from "../../../shared/components/ui";
import type { ManualOrderBody, ManualOrderCandidates } from "../types/manual-order";
import type { ConfirmBody, InvoiceItem, InvoiceMatching, MatchingGroup } from "../types/matching";
import { AllocationCard } from "./AllocationCard";
import { groupAllocations } from "./allocation-groups";
import { GroupComparisonCard } from "./GroupComparisonCard";
import { LinkedAllocations } from "./LinkedAllocations";
import { ManualAllocation } from "./ManualAllocation";

type Actions = {
  confirm: (id: string, body: ConfirmBody) => void;
  reverify: (id: string, body: ConfirmBody) => void;
  reject: (id: string, note: string) => void;
  cancel: (id: string, reason: string) => Promise<boolean>;
  create: (body: ManualOrderBody) => Promise<boolean>;
  search: (keyword: string) => Promise<ManualOrderCandidates>;
  confirmGroup: (groupId: string, note: string) => Promise<boolean>;
  rejectGroup: (groupId: string, note: string) => Promise<boolean>;
};

/** 选中发票行的详情：整单比对、手动关联、已关联、其他待处理建议与历史记录。 */
export function InvoiceLinePanel({
  item,
  invoiceId,
  invoiceVersionId,
  replacements,
  busy,
  actions,
  invoice,
  groups,
}: {
  item: InvoiceItem;
  invoiceId: string;
  invoiceVersionId: string | null;
  replacements: { id: string; label: string }[];
  busy: boolean;
  actions: Actions;
  invoice: InvoiceMatching["invoice"];
  groups: MatchingGroup[];
}) {
  const [manual, setManual] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  // 整单建议整组展示与审核，组内逐条记录不再单独列为待处理比对
  const own = groups.filter((group) => group.items.some((row) => row.invoiceItemId === item.id));
  const inGroups = new Set(own.flatMap((group) => group.allocationIds));
  const { linked, pending, history } = groupAllocations(
    item.allocations.filter((allocation) => !inGroups.has(allocation.id)),
  );
  // 一次只展开一条待处理比对；处理后列表变化时回到第一条。
  const active = pending.find((row) => row.id === activeId) ?? pending[0];
  const card = (allocation: (typeof pending)[number]) => (
    <AllocationCard
      key={`${allocation.id}:${allocation.status}:${allocation.verificationStatus}:${allocation.currentInvoiceVersionId}`}
      allocation={allocation}
      invoice={invoice}
      item={item}
      busy={busy}
      onConfirm={(body) => actions.confirm(allocation.id, body)}
      onReverify={(body) => actions.reverify(allocation.id, body)}
      onReject={(note) => actions.reject(allocation.id, note)}
      onCancel={(reason) => void actions.cancel(allocation.id, reason)}
    />
  );
  return (
    <section className="matching-line-panel" aria-label="发票行比对">
      {own.map((group) => (
        <GroupComparisonCard
          key={`${group.id}:${group.confidence}:${group.confirm.allowed}`}
          group={group}
          item={item}
          invoice={invoice}
          busy={busy}
          onConfirm={(note) => actions.confirmGroup(group.id, note)}
          onReject={(note) => actions.rejectGroup(group.id, note)}
        />
      ))}
      {pending.length > 1 && (
        <Card aria-label="待处理比对">
          <CardHeader
            title={`待处理比对（${pending.length}）`}
            description="同一发票行拆分到多条子采购行时逐条核对；选择一条在下方查看逐项比对。"
          />
          <ul className="matching-proposals">
            {pending.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="matching-proposal"
                  aria-current={row.id === active?.id ? "true" : undefined}
                  disabled={busy}
                  onClick={() => setActiveId(row.id)}
                >
                  <span className="matching-proposal__title">
                    <strong>{row.purchase?.orderNo || "待核对子采购行"}</strong>
                    <Badge tone={row.tier === "high" ? "success" : row.tier === "low" ? "danger" : "warning"}>
                      {row.confidence === null ? row.statusLabel : `${row.confidence}%`}
                    </Badge>
                  </span>
                  <small>
                    {row.purchase?.item || "—"} {row.purchase?.specification || ""}
                  </small>
                  <span className="matching-proposal__amount">
                    {row.quantity} {item.unit || ""} · 含税 {row.amount}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {active
        ? card(active)
        : own.length === 0 && (
            <Card>
              <EmptyState
                title="本行没有待审核建议"
                description="只有整张子采购单的数量、含税合计与发票行完全一致时才自动建议；部分开票或单位不同请手动关联。"
              />
            </Card>
          )}
      <Card aria-label="候选子采购单">
        <CardHeader
          title="候选子采购单"
          description="以整张子采购单为最小关联单位，选择后展开该单明细填写本票分配。已有待审核建议时，请先驳回再手动关联；已通过的关联可选择替换。"
          actions={
            <Button disabled={busy} aria-expanded={manual} onClick={() => setManual(!manual)}>
              {manual ? "收起手动关联" : "手动关联"}
            </Button>
          }
        />
        <CardContent>
          <ManualAllocation
            key={item.allocations.map((row) => `${row.id}:${row.status}:${row.verificationStatus}`).join("|")}
            invoiceId={invoiceId}
            invoiceVersionId={invoiceVersionId}
            item={item}
            busy={busy}
            search={actions.search}
            replacements={replacements}
            onCreate={actions.create}
            showForm={manual}
            onShowForm={() => setManual(true)}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader
          title={`已关联（${linked.length}）`}
          description={`已占用（含待复核）：数量 ${item.confirmedQuantity} · 含税 ${item.confirmedAmount}`}
        />
        <CardContent>
          <LinkedAllocations allocations={linked} busy={busy} onCancel={actions.cancel} />
        </CardContent>
      </Card>
      {history.length > 0 && (
        <details className="matching-history">
          <summary>已驳回或已取消的记录（{history.length}）</summary>
          {history.map(card)}
        </details>
      )}
    </section>
  );
}
