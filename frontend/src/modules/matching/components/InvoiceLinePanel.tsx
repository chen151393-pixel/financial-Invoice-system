import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { Candidate, ConfirmBody, InvoiceItem, ManualBody } from "../types/matching";
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
}: {
  item: InvoiceItem;
  invoiceId: string;
  invoiceVersionId: string | null;
  replacements: { id: string; label: string }[];
  busy: boolean;
  actions: Actions;
}) {
  const [manual, setManual] = useState(false);
  const { linked, pending, history } = groupAllocations(item.allocations);
  const card = (allocation: (typeof pending)[number]) => (
    <AllocationCard
      key={`${allocation.id}:${allocation.status}:${allocation.verificationStatus}:${allocation.currentInvoiceVersionId}`}
      allocation={allocation}
      busy={busy}
      onConfirm={(body) => actions.confirm(allocation.id, body)}
      onReverify={(body) => actions.reverify(allocation.id, body)}
      onReject={(note) => actions.reject(allocation.id, note)}
      onCancel={(reason) => void actions.cancel(allocation.id, reason)}
    />
  );
  return (
    <section className="matching-panel matching-panel--flush matching-line-panel" aria-label="发票行比对">
      <div className="matching-panel__head">
        <h2>
          {!item.active && "【历史明细】"}
          {item.lineNo}. {item.item ?? "—"} {item.specification && `· ${item.specification}`}
        </h2>
        <Button
          variant={manual ? "secondary" : "primary"}
          disabled={busy}
          aria-expanded={manual}
          onClick={() => setManual(!manual)}
        >
          {manual ? "收起手动关联" : "＋ 手动关联子采购行"}
        </Button>
      </div>
      <dl className="matching-line-sum">
        <div>
          <dt>数量</dt>
          <dd>
            {item.quantity ?? "—"} {item.unit ?? ""}
          </dd>
        </div>
        <div>
          <dt>含税金额</dt>
          <dd>{item.amount ?? "—"}</dd>
        </div>
        <div>
          <dt>已占用（含待复核）</dt>
          <dd>
            {item.confirmedQuantity} / {item.confirmedAmount}
          </dd>
        </div>
      </dl>
      <div className="matching-body">
        {manual && (
          <section className="matching-manual" aria-label="手动关联子采购行">
            <h3>手动关联子采购行</h3>
            <ManualAllocation
              invoiceId={invoiceId}
              invoiceVersionId={invoiceVersionId}
              item={item}
              busy={busy}
              search={actions.search}
              replacements={replacements}
              onCreate={(body, replaceId, reason) =>
                actions.create(body, replaceId, reason).then((saved) => {
                  if (saved) setManual(false);
                  return saved;
                })
              }
            />
          </section>
        )}
        <h3 className="matching-subhead">已关联（{linked.length}）</h3>
        <LinkedAllocations allocations={linked} busy={busy} onCancel={actions.cancel} />
        <h3 className="matching-subhead">待处理（{pending.length}）</h3>
        {pending.length === 0 ? (
          <p className="matching-help">暂无待审核建议或需重新核实的分配。</p>
        ) : (
          pending.map(card)
        )}
        {history.length > 0 && (
          <details className="matching-history">
            <summary>已驳回或已取消的记录（{history.length}）</summary>
            {history.map(card)}
          </details>
        )}
      </div>
    </section>
  );
}
