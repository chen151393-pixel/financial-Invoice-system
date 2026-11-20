import { useId, useRef, useState } from "react";
import { HttpError } from "../../../shared/api/http";
import { Alert, Button, Dialog, Field } from "../../../shared/components/ui";
import { createBatch } from "../api";
import "./create-batch-dialog.css";
import { useHkReceiptPreview } from "../hooks/useHkReceiptPreview";
import { money } from "../../../shared/format/money";
import type { HkPending } from "../types/hk-workbench";

/** 登记一笔回款：金额、手续费按银行水单填写；报关合计与差额由后端核对后在批次详情中展示。 */
export function CreateBatchDialog({
  declarationNos,
  defaultAmount,
  onClose,
  onCreated,
  selectedRows,
  onRemove,
}: {
  declarationNos: string[];
  defaultAmount: string;
  onClose: () => void;
  onCreated: (id: number) => void;
  selectedRows?: HkPending[];
  onRemove?: (number: string) => void;
}) {
  // 同一次弹窗内重复提交使用同一幂等号，后端返回同一批次
  const requestId = useRef(crypto.randomUUID());
  const submitting = useRef(false);
  const id = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Readonly<Record<string, string>>>({});

  const [amountText, setAmountText] = useState(defaultAmount);
  const [feeText, setFeeText] = useState("0");
  const preview = useHkReceiptPreview(declarationNos, amountText, feeText);

  async function submit(form: HTMLFormElement) {
    if (submitting.current) return;
    submitting.current = true;
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      const batch = await createBatch({
        requestId: requestId.current,
        declarationNos,
        receivedOn: value("receivedOn"),
        receivedAmount: value("receivedAmount"),
        receivedFee: value("receivedFee") || "0",
        payer: value("payer"),
        receivingAccount: value("receivingAccount"),
        receivedReference: value("receivedReference"),
        note: value("note"),
      });
      onCreated(batch.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建批次失败，请稍后重试");
      if (reason instanceof HttpError) {
        setFieldErrors(reason.fieldErrors);
        const field = form.elements.namedItem(Object.keys(reason.fieldErrors)[0] ?? "");
        if (field instanceof HTMLInputElement) {
          // 提交期间字段不可编辑，等 disabled 解除后再聚焦后端标记的字段。
          requestAnimationFrame(() => field.focus());
        }
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <Dialog title="登记回款并建结汇批次" onClose={onClose} busy={busy} className="settlement-create-dialog">
      <form
        className="settlement-create"
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault();
          void submit(event.currentTarget);
        }}
      >
        <details className="settlement-create__selection" open={declarationNos.length <= 3}>
          <summary>已选 {declarationNos.length} 张报关单</summary>
          <ul>
            {declarationNos.map((number) => (
              <li key={number} className="settlement-create__selected-row">
                <span>
                  <strong>{number}</strong>
                  {selectedRows?.find((row) => row.declarationNo === number) && (
                    <small>
                      {selectedRows.find((row) => row.declarationNo === number)?.consignee} ·{" "}
                      {selectedRows.find((row) => row.declarationNo === number)?.exportDate} ·{" "}
                      {selectedRows.find((row) => row.declarationNo === number)?.currency}{" "}
                      {selectedRows.find((row) => row.declarationNo === number)?.amount}
                    </small>
                  )}
                </span>
                {onRemove && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy || declarationNos.length <= 1}
                    onClick={() => onRemove(number)}
                  >
                    移除
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </details>
        <fieldset className="settlement-create__section" disabled={busy}>
          <legend>回款信息</legend>
          <p className="settlement-create__hint" id={`${id}-amount-hint`}>
            按银行水单填写。金额支持千分位，最多两位小数；到账金额 +
            手续费须等于报关合计，系统将在保存后核对。
          </p>
          <Field label="到账日期（必填）">
            <input name="receivedOn" type="date" required />
          </Field>
          <Field label="到账金额（必填）">
            <input
              name="receivedAmount"
              inputMode="decimal"
              required
              defaultValue={defaultAmount}
              onChange={(event) => setAmountText(event.target.value)}
              placeholder="如 10,002.59"
              aria-invalid={!!fieldErrors.receivedAmount || undefined}
              aria-describedby={`${id}-amount-hint${fieldErrors.receivedAmount ? ` ${id}-amount-error` : ""}`}
            />
            {fieldErrors.receivedAmount && (
              <small className="settlement-create__error" id={`${id}-amount-error`}>
                {fieldErrors.receivedAmount}
              </small>
            )}
          </Field>
          <Field label="银行手续费">
            <input
              name="receivedFee"
              onChange={(event) => setFeeText(event.target.value)}
              inputMode="decimal"
              defaultValue="0"
              aria-invalid={!!fieldErrors.receivedFee || undefined}
              aria-describedby={fieldErrors.receivedFee ? `${id}-fee-error` : undefined}
            />
            {fieldErrors.receivedFee && (
              <small className="settlement-create__error" id={`${id}-fee-error`}>
                {fieldErrors.receivedFee}
              </small>
            )}
          </Field>
        </fieldset>
        <fieldset className="settlement-create__section settlement-create__bank" disabled={busy}>
          <legend>收款凭证</legend>
          <div className="settlement-create__wide">
            <Field label="付款方">
              <input name="payer" maxLength={500} placeholder="填写银行流水中的付款方全称" />
            </Field>
          </div>
          <Field label="收款账户">
            <input name="receivingAccount" maxLength={200} placeholder="填写实际收款账户" />
          </Field>
          <Field label="流水号 / NS 收款单号">
            <input name="receivedReference" maxLength={200} placeholder="填写银行流水号或收款单号" />
          </Field>
          <div className="settlement-create__wide">
            <Field label="说明（选填）">
              <textarea name="note" maxLength={500} rows={2} placeholder="补充本次回款的备注" />
            </Field>
          </div>
        </fieldset>
        <div className="settlement-create__preview" aria-live="polite">
          {preview.loading ? (
            <p>正在核对已选报关金额与香港到账…</p>
          ) : preview.result ? (
            <Alert
              tone={preview.result.balanced ? "success" : "warning"}
              title={preview.result.balanced ? "香港到账已对平" : "香港到账待核对"}
            >
              已选报关合计 {preview.result.currency} {money(preview.result.declaredTotal)} · 到账 + 手续费{" "}
              {money(preview.result.arrivedTotal)} · 差额 {money(preview.result.difference)}
              {!preview.result.balanced && <p>可先登记实际到账，金额未对平时不能确认资料已出。</p>}
              {preview.result.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </Alert>
          ) : (
            <Alert tone="danger">{preview.error}</Alert>
          )}
        </div>
        {error && (
          <Alert tone="danger" title="登记未完成，填写内容已保留">
            {error}
          </Alert>
        )}
        <div className="settlement-create__actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || preview.loading || !preview.result?.submit.allowed}
          >
            {busy ? "正在登记…" : "登记并建批次"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
