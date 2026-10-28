import { useState } from "react";
import { Button, Card, CardContent, CardHeader, EmptyState } from "../../../shared/components/ui";
import type { Candidate, ConfirmBody, InvoiceItem, InvoiceMatching, ManualBody } from "../types/matching";
import { AllocationCard } from "./AllocationCard";
import { groupAllocations } from "./allocation-groups";
import { LinkedAllocations } from "./LinkedAllocations";
import { ManualAllocation } from "./ManualAllocation";

type Actions = {
  confirm: (id: string, body: ConfirmBody) => void;
  reverify: (id: string, body: ConfirmBody) => void;
  reject: (id: string, note: string) => void;
  cancel: (id: string, reason: string) => Promise<boolean>;
  create: (body: ManualBody, replaceId: string, reason: string) => Promise<boolean>;
  search: (keyword: string) => Promise<{ rows: Candidate[]; total: number }>;
};

/** 选中发票行的详情：手动关联、已关联、待处理建议与历史记录。 */
export function InvoiceLinePanel({
  item,
  invoiceId,
  invoiceVersionId,
  replacements,
  busy,
  actions,
  invoice,
}: {
  item: InvoiceItem;
  invoiceId: string;
  invoiceVersionId: string | null;
  replacements: { id: string; label: string }[];
  busy: boolean;
  actions: Actions;
  invoice: InvoiceMatching["invoice"];
}) {
  const [manual, setManual] = useState(false);
  const { linked, pending, history } = groupAllocations(item.allocations);
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
      {pending.length > 0 ? (
        pending.map(card)
      ) : (
        <Card>
          <EmptyState
            title="本行没有待审核建议"
            description="可在下方查看已关联记录或选择子采购行手动关联。"
          />
        </Card>
      )}
      <Card aria-label="候选子采购行">
        <CardHeader
          title="候选子采购行"
          description="已有待审核建议时，请先驳回再手动关联；已通过的关联可选择替换。"
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
