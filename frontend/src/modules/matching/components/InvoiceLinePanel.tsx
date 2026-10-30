import { useState } from "react";
import { Badge, Card, CardContent, CardHeader, EmptyState } from "../../../shared/components/ui";
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
  linkedGroups = [],
}: {
  item: InvoiceItem;
  invoiceId: string;
  invoiceVersionId: string | null;
  replacements: { id: string; label: string }[];
  busy: boolean;
  actions: Actions;
  invoice: InvoiceMatching["invoice"];
  groups: MatchingGroup[];
  linkedGroups?: MatchingGroup[];
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  // 整单建议整组展示与审核，组内逐条记录不再单独列为待处理比对
  const own = groups.filter((group) => group.items.some((row) => row.invoiceItemId === item.id));
  const inGroups = new Set(own.flatMap((group) => group.allocationIds));
  const linkedOwn = linkedGroups.filter((group) => group.items.some((row) => row.invoiceItemId === item.id));
  const linkedGroupedIds = new Set(linkedOwn.flatMap((group) => group.allocationIds));
  const { linked, pending, history } = groupAllocations(
    item.allocations.filter((allocation) => !inGroups.has(allocation.id)),
  );
  // 一次只展开一条待处理比对；处理后列表变化时回到第一条。
  const active = pending.find((row) => row.id === activeId) ?? pending[0];
  // 没有建议也没有已关联时，手动关联占据建议位置并默认展示置信度最高的候选
  const autoLoad = own.length === 0 && pending.length === 0 && linked.length === 0;
  const card = (allocation: (typeof pending)[number], readOnly = false) => (
    <AllocationCard
      key={`${allocation.id}:${allocation.status}:${allocation.verificationStatus}:${allocation.currentInvoiceVersionId}`}
      allocation={allocation}
      invoice={invoice}
      item={item}
      readOnly={readOnly}
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
      {active && card(active)}
      {linkedOwn.map((group) => (
        <GroupComparisonCard
          key={`linked:${group.id}`}
          group={group}
          item={item}
          invoice={invoice}
          busy={busy}
          readOnly
          reviewedAllocations={linked.filter((allocation) => group.allocationIds.includes(allocation.id))}
          onConfirm={(note) => actions.confirmGroup(group.id, note)}
          onReject={(note) => actions.rejectGroup(group.id, note)}
        />
      ))}
      {linked
        .filter((allocation) => !linkedGroupedIds.has(allocation.id))
        .map((allocation) => card(allocation, true))}
      {!active && own.length === 0 && linked.length === 0 && !autoLoad && (
        <Card>
          <EmptyState
            title="本行没有待审核建议"
            description="系统按整张发票对应整张子采购单生成建议；没有建议时请手动关联。一张子采购单只能由一张发票开具，发票少开的差额在关联后按差异结束。"
          />
        </Card>
      )}
      <ManualAllocation
        key={[
          item.id,
          ...item.allocations.map((row) => `${row.id}:${row.status}:${row.verificationStatus}`),
        ].join("|")}
        invoiceId={invoiceId}
        invoiceVersionId={invoiceVersionId}
        item={item}
        invoice={invoice}
        busy={busy}
        search={actions.search}
        replacements={replacements}
        onCreate={actions.create}
        autoLoad={autoLoad}
      />
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
          {history.map((allocation) => card(allocation))}
        </details>
      )}
    </section>
  );
}
