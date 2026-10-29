import { useRef, useState } from "react";
import { Button, Card, CardContent, CardHeader, Field } from "../../../shared/components/ui";
import type { ConfirmBody, TaskDetail } from "../types";

export function PlanForm({
  task,
  busy,
  onConfirm,
}: {
  task: TaskDetail;
  busy: boolean;
  onConfirm: (body: ConfirmBody) => void;
}) {
  const [selectedBills, setSelectedBills] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const requestId = useRef("");
  const bills = task.candidates?.purchaseOrders.flatMap((order) => order.bills) ?? [];
  return (
    <Card>
      <CardHeader title="确认账单分配" description="每张子采购单选择一张账单；同一账单的金额汇总回写。" />
      <CardContent>
        <form
          className="wb-plan-fields"
          onSubmit={(event) => {
            event.preventDefault();
            if (!confirmed || busy) return;
            requestId.current ||= crypto.randomUUID();
            onConfirm({
              requestId: requestId.current,
              revision: task.revision,
              confirmScope: true,
              evidence,
              orders: task.orders.map(({ subPurchaseOrderId }) => ({
                subPurchaseOrderId,
                billId: selectedBills[subPurchaseOrderId] || "",
              })),
            });
          }}
        >
          <fieldset disabled={busy} className="wb-plan-fields">
            <legend className="ui-sr-only">账单分配明细</legend>
            {task.orders.map((row) => (
              <div className="wb-plan-row" key={row.subPurchaseOrderId}>
                <Field label="子采购单">
                  <input readOnly value={row.orderNo} />
                </Field>
                <Field label="目标账单">
                  <select
                    required
                    aria-label={`${row.orderNo} 的目标账单`}
                    value={selectedBills[row.subPurchaseOrderId] || ""}
                    onChange={(e) => {
                      requestId.current = "";
                      setSelectedBills((current) => ({
                        ...current,
                        [row.subPurchaseOrderId]: e.target.value,
                      }));
                    }}
                  >
                    <option value="">请选择账单</option>
                    {bills
                      .filter((bill) => row.eligibleBillIds.includes(bill.billId))
                      .map((bill) => (
                        <option key={bill.billId} value={bill.billId}>
                          {bill.billNumber} · 子公司 {bill.subsidiaryId}
                        </option>
                      ))}
                  </select>
                </Field>
                <Field label="含税金额（元）">
                  <input readOnly value={row.amount} />
                </Field>
              </div>
            ))}
            <Field label="公司与账单归属核实依据">
              <textarea
                required
                minLength={5}
                maxLength={1000}
                rows={3}
                value={evidence}
                placeholder="填写已核实的实际 NS 采购子公司、账单与子采购的归属及凭据"
                onChange={(e) => {
                  requestId.current = "";
                  setEvidence(e.target.value);
                }}
              />
            </Field>
            <label className="wb-check">
              <input
                type="checkbox"
                required
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              已核实票面购买方对应的实际 NS 子公司，以及各账单和子采购的归属
            </label>
            <Button variant="primary" type="submit" disabled={!confirmed || !task.actions.confirm}>
              确认并冻结方案
            </Button>
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
