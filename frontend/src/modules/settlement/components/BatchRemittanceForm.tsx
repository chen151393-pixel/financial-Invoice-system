import { Alert, Badge, Button, Card, CardContent, CardHeader, Field } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BatchDetail, RemittanceBody } from "../types";

/** 只收集汇回信息；金额核对、手续费提醒和结汇许可全部使用后端结果。 */
export function BatchRemittanceForm({
  batch,
  busy,
  onSubmit,
  onCancel,
}: {
  batch: BatchDetail;
  busy: boolean;
  onSubmit: (body: RemittanceBody) => void;
  onCancel: () => void;
}) {
  const allowed = batch.actions.settle.allowed;
  return (
    <Card>
      <CardHeader
        title="登记汇回境内"
        description="按银行实际到账记录填写，金额及手续费由系统重新核对。"
        actions={<Badge tone={batch.status === "settled" ? "success" : "info"}>{batch.statusLabel}</Badge>}
      />
      <CardContent className="settlement-detail">
        {!allowed && (
          <Alert tone="info" title="当前汇回状态">
            {batch.actions.settle.reason}
          </Alert>
        )}
        {batch.remittedOn && (
          <dl className="settlement-detail__facts">
            <dt>汇回日期 / 境内到账</dt>
            <dd>
              {batch.remittedOn} · {batch.currency} {money(batch.remittedAmount)}
            </dd>
            <dt>汇回手续费</dt>
            <dd>
              {batch.currency} {money(batch.remittedFee)}
            </dd>
            <dt>汇回流水号</dt>
            <dd>{batch.remittedReference || "—"}</dd>
            <dt>经办</dt>
            <dd>{batch.settledBy || "—"}</dd>
          </dl>
        )}
        {batch.balances.map((balance) => (
          <Alert
            key={balance.stage}
            tone={balance.balanced ? (balance.warnings.length ? "warning" : "success") : "danger"}
            title={`${balance.label}核对：${balance.balanced ? "已对平" : `差额 ${balance.difference}`}`}
          >
            {balance.warnings.length ? balance.warnings.join("；") : "到账加手续费等于报关合计。"}
          </Alert>
        ))}
        {!batch.remittedOn && (
          <form
            className="settlement-form"
            aria-label="登记汇回境内"
            aria-busy={busy}
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const value = (key: string) => String(data.get(key) || "").trim();
              onSubmit({
                remittedOn: value("remittedOn"),
                remittedAmount: value("remittedAmount"),
                remittedFee: value("remittedFee"),
                remittedReference: value("remittedReference"),
              });
            }}
          >
            <Field label="汇回日期">
              <input name="remittedOn" type="date" disabled={busy || !allowed} />
            </Field>
            <Field label={`境内到账金额（${batch.currency}）`}>
              <input name="remittedAmount" inputMode="decimal" disabled={busy || !allowed} />
            </Field>
            <Field label={`汇回手续费（${batch.currency}）`}>
              <input name="remittedFee" inputMode="decimal" defaultValue="0" disabled={busy || !allowed} />
            </Field>
            <Field label="汇回流水号">
              <input name="remittedReference" maxLength={200} disabled={busy || !allowed} />
            </Field>
            <div className="settlement-form__actions">
              <Button onClick={onCancel} disabled={busy}>
                返回资料办理
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={busy || !allowed}
                title={batch.actions.settle.reason}
              >
                {busy ? "正在登记…" : "登记汇回并确认结汇"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
