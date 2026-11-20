import { useId, useRef } from "react";
import { Button, Card, CardContent, CardHeader, Field } from "../../../shared/components/ui";
import type { BankSlipUpload, HkReceiptFields as Fields } from "../types/hk-receipt";
export function HkReceiptFields({
  fields,
  payer,
  currency,
  accounts,
  busy,
  readingFile,
  errors,
  bankSlip,
  onChange,
  onFile,
}: {
  fields: Fields;
  payer: string;
  currency: string;
  accounts: string[];
  busy: boolean;
  readingFile: boolean;
  errors: Readonly<Record<string, string>>;
  bankSlip: BankSlipUpload | null;
  onChange: (key: keyof Fields, value: string) => void;
  onFile: (file: File) => void;
}) {
  const id = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const disabled = busy || readingFile;
  const input = (key: Exclude<keyof Fields, "payer">, type = "text") => (
    <input
      name={key}
      type={type}
      aria-invalid={!!errors[key] || undefined}
      aria-describedby={errors[key] ? `${id}-${key}-error` : undefined}
      inputMode={key === "receivedAmount" || key === "receivedFee" ? "decimal" : undefined}
      value={fields[key]}
      onChange={(event) => onChange(key, event.target.value)}
    />
  );
  return (
    <Card>
      <CardHeader
        title="2 · 登记香港到账流水"
        description="请按实际到账流水人工填写，银行水单 PDF 可作为附件随批次保存。"
      />
      <CardContent>
        <fieldset className="hk-receipt__fields" disabled={disabled}>
          <Field label="到账日期（必填）">
            {input("receivedOn", "date")}
            {errors.receivedOn && (
              <small className="hk-receipt__error" id={`${id}-receivedOn-error`}>
                {errors.receivedOn}
              </small>
            )}
          </Field>
          <Field label={`到账金额 ${currency}（必填）`}>
            {input("receivedAmount")}
            {errors.receivedAmount && (
              <small className="hk-receipt__error" id={`${id}-receivedAmount-error`}>
                {errors.receivedAmount}
              </small>
            )}
          </Field>
          <Field label={`银行手续费 ${currency}`}>
            {input("receivedFee")}
            {errors.receivedFee && (
              <small className="hk-receipt__error" id={`${id}-receivedFee-error`}>
                {errors.receivedFee}
              </small>
            )}
          </Field>
          <Field label="付款方">
            <input
              name="payer"
              maxLength={500}
              value={payer}
              onChange={(e) => onChange("payer", e.target.value)}
            />
          </Field>
          <Field label="收款账户">
            <input
              name="receivingAccount"
              maxLength={200}
              list="hk-receiving-accounts"
              value={fields.receivingAccount}
              onChange={(e) => onChange("receivingAccount", e.target.value)}
              placeholder="选择历史账户或填写实际账户"
            />
            <datalist id="hk-receiving-accounts">
              {accounts.map((account) => (
                <option key={account} value={account} />
              ))}
            </datalist>
          </Field>
          <Field label="水单流水号">
            <input
              name="receivedReference"
              maxLength={200}
              value={fields.receivedReference}
              onChange={(e) => onChange("receivedReference", e.target.value)}
            />
          </Field>
          <div className="hk-receipt__slip">
            <input
              ref={fileInput}
              type="file"
              hidden
              accept="application/pdf,.pdf"
              aria-label="选择银行水单 PDF"
              onChange={(e) => {
                const file = e.currentTarget.files?.[0];
                e.currentTarget.value = "";
                if (file) onFile(file);
              }}
            />
            <div>
              <strong>银行水单</strong>
              <p>
                {readingFile
                  ? "正在读取水单文件…"
                  : bankSlip
                    ? `${bankSlip.fileName} · 已选择，提交时随批次保存`
                    : "可选择 PDF 原件，提交时随批次保存。"}
              </p>
            </div>
            <Button size="sm" type="button" disabled={disabled} onClick={() => fileInput.current?.click()}>
              {bankSlip ? "更换水单" : "选择水单 PDF"}
            </Button>
          </div>
          <div className="hk-receipt__wide">
            <Field label="说明（选填）">
              <textarea
                name="note"
                maxLength={500}
                rows={2}
                value={fields.note}
                onChange={(e) => onChange("note", e.target.value)}
              />
            </Field>
          </div>
        </fieldset>
      </CardContent>
    </Card>
  );
}
