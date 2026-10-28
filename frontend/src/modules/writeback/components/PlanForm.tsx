import { useRef, useState } from "react";
import { Button, Card, CardContent, CardHeader, Field } from "../../../shared/components/ui";
import type { ConfirmBody, TaskDetail, TargetLine } from "../types";

export function PlanForm({
  task,
  busy,
  onConfirm,
}: {
  task: TaskDetail;
  busy: boolean;
  onConfirm: (body: ConfirmBody) => void;
}) {
  const [lines, setLines] = useState<(TargetLine & { key: string })[]>(
    task.allocations.map((row) => ({
      allocationId: row.allocationId,
      amount: row.amount,
      billId: "",
      key: crypto.randomUUID(),
    })),
  );
  const [evidence, setEvidence] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const requestId = useRef("");
  const bills = task.candidates?.purchaseOrders.flatMap((order) => order.bills) ?? [];
  function edit(index: number, patch: Partial<TargetLine>) {
    requestId.current = "";
    setLines((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }
  return (
    <Card>
      <CardHeader
        title="确认账单分配"
        description="逐条填写审核金额的去向。若拆分到多张账单，请新增分配行；金额合计与额度由后端校验。"
      />
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
              allocations: lines.map(({ allocationId, billId, amount }) => ({
                allocationId,
                billId,
                amount,
              })),
            });
          }}
        >
          <fieldset disabled={busy} className="wb-plan-fields">
            <legend className="ui-sr-only">账单分配明细</legend>
            {lines.map((row, index) => (
              <div className="wb-plan-row" key={row.key}>
                <Field label={`第 ${index + 1} 笔审核分配`}>
                  <select
                    value={row.allocationId}
                    onChange={(e) => edit(index, { allocationId: e.target.value })}
                  >
                    {task.allocations.map((a) => (
                      <option key={a.allocationId} value={a.allocationId}>
                        {a.orderNo} · 分配 {a.allocationId} · {a.amount} 元
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="目标账单">
                  <select
                    required
                    value={row.billId}
                    onChange={(e) => edit(index, { billId: e.target.value })}
                  >
                    <option value="">请选择账单</option>
                    {bills.map((bill) => (
                      <option key={bill.billId} value={bill.billId}>
                        {bill.billNumber} · 子公司 {bill.subsidiaryId}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="含税金额（元）">
                  <input
                    required
                    inputMode="decimal"
                    pattern="(?:0|[1-9][0-9]*)\.[0-9]{2}"
                    value={row.amount}
                    onChange={(e) => edit(index, { amount: e.target.value })}
                  />
                </Field>
                <Button
                  onClick={() => {
                    requestId.current = "";
                    setLines((rows) => rows.filter((_, i) => i !== index));
                  }}
                >
                  移除
                </Button>
              </div>
            ))}
            <Button
              onClick={() => {
                requestId.current = "";
                setLines((rows) => [
                  ...rows,
                  {
                    key: crypto.randomUUID(),
                    allocationId: task.allocations[0].allocationId,
                    billId: "",
                    amount: "",
                  },
                ]);
              }}
            >
              新增分配行
            </Button>
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
