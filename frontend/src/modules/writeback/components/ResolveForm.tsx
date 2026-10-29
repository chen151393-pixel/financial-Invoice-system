import { useState } from "react";
import { Alert, Button, Card, CardContent, CardHeader, Field } from "../../../shared/components/ui";
import type { ResolveBody, TaskDetail } from "../types";

// 结果不明或部分完成：只能在 NS 核实后登记结论，本系统不提供直接重发。
export function ResolveForm({
  task,
  busy,
  onResolve,
}: {
  task: TaskDetail;
  busy: boolean;
  onResolve: (body: ResolveBody) => void;
}) {
  const [outcome, setOutcome] = useState<ResolveBody["outcome"]>("applied");
  const [evidence, setEvidence] = useState("");
  const [recordId, setRecordId] = useState(task.request?.nsRecordId ?? "");
  const [checked, setChecked] = useState(false);
  return (
    <Card>
      <CardHeader
        title="核实 NS 写入结果"
        description={`请在 NS 按发票号码 ${task.invoiceNo} 和供应商查找发票记录，并核对相关账单的累计已收发票金额。`}
      />
      <CardContent>
        <Alert tone="warning" title={task.stateLabel}>
          {task.reason}
        </Alert>
        <form
          className="wb-plan-fields"
          onSubmit={(event) => {
            event.preventDefault();
            if (!checked || busy) return;
            onResolve({
              revision: task.revision,
              outcome,
              evidence,
              nsRecordId: outcome === "applied" && recordId ? recordId : null,
            });
          }}
        >
          <fieldset disabled={busy} className="wb-plan-fields">
            <legend className="ui-sr-only">核实结论</legend>
            <label className="wb-check">
              <input
                type="radio"
                name="outcome"
                checked={outcome === "applied"}
                onChange={() => setOutcome("applied")}
              />
              NS 已完整登记（发票记录、明细及全部账单累计都已核对）
            </label>
            {task.actions.markNotWritten && (
              <label className="wb-check">
                <input
                  type="radio"
                  name="outcome"
                  checked={outcome === "not_written"}
                  onChange={() => setOutcome("not_written")}
                />
                NS 没有任何写入，可重新写入
              </label>
            )}
            {outcome === "applied" && (
              <Field label="NS 供应商发票记录 ID（选填）">
                <input
                  inputMode="numeric"
                  pattern="[1-9][0-9]{0,19}"
                  value={recordId}
                  onChange={(event) => setRecordId(event.target.value)}
                />
              </Field>
            )}
            <Field label="核实依据">
              <textarea
                required
                minLength={5}
                maxLength={1000}
                rows={3}
                value={evidence}
                placeholder="填写在 NS 查到的记录、账单累计及核对人"
                onChange={(event) => setEvidence(event.target.value)}
              />
            </Field>
            <label className="wb-check">
              <input
                type="checkbox"
                required
                checked={checked}
                onChange={(event) => setChecked(event.target.checked)}
              />
              已在 NS 页面实际核对，结论如上
            </label>
            <div>
              <Button variant="primary" type="submit" disabled={!checked}>
                提交核实结果
              </Button>
            </div>
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
