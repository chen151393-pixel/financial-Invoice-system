import { useId, useRef, useState } from "react";
import { HttpError } from "../../../shared/api/http";
import { Alert, Button, Dialog, Field } from "../../../shared/components/ui";
import { saveParty } from "../api";
import type { Party } from "../types";
import "./party-dialog.css";

/** 新增和修改共用统一表单；字段校验与重名判断由后端返回。 */
export function PartyDialog({
  party,
  onClose,
  onSaved,
}: {
  party: Party | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Readonly<Record<string, string>>>({});
  const submitting = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const id = useId();
  const describedBy = (name: string, hint?: string) =>
    [hint, fieldErrors[name] ? `${id}-${name}-error` : ""].filter(Boolean).join(" ") || undefined;
  const fieldError = (name: string) =>
    fieldErrors[name] && (
      <small className="settlement-party-dialog__error" id={`${id}-${name}-error`}>
        {fieldErrors[name]}
      </small>
    );

  async function submit(form: HTMLFormElement) {
    if (submitting.current) return;
    submitting.current = true;
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    setBusy(true);
    setError("");
    setFieldErrors({});
    try {
      await saveParty({
        id: party?.id ?? null,
        name: value("name"),
        nameCn: value("nameCn"),
        nameEn: value("nameEn"),
        addressCn: value("addressCn"),
        addressEn: value("addressEn"),
        phone: value("phone"),
      });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请稍后重试");
      if (reason instanceof HttpError) {
        setFieldErrors(reason.fieldErrors);
        const field = formRef.current?.elements.namedItem(Object.keys(reason.fieldErrors)[0] || "");
        if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) {
          requestAnimationFrame(() => field.focus());
        }
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={party ? "修改合同抬头" : "新增合同抬头"}
      onClose={onClose}
      busy={busy}
      className="settlement-party-dialog"
    >
      <form
        ref={formRef}
        className="settlement-party-dialog__form"
        aria-label={party ? "修改合同抬头" : "新增合同抬头"}
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault();
          void submit(event.currentTarget);
        }}
      >
        <fieldset className="settlement-party-dialog__fields" disabled={busy}>
          <div className="settlement-party-dialog__wide">
            <Field label="匹配名称（必填）">
              <input
                name="name"
                required
                maxLength={300}
                defaultValue={party?.name}
                placeholder="填写来源单据中的完整公司名称"
                aria-invalid={!!fieldErrors.name || undefined}
                aria-describedby={describedBy("name", `${id}-matching-hint`)}
              />
              <small className="settlement-party-dialog__hint" id={`${id}-matching-hint`}>
                买方须与海关回执的境外收货人一致；卖方须与 NS 报关单的申报抬头一致。
              </small>
              {fieldError("name")}
            </Field>
          </div>
          <div className="settlement-party-dialog__wide">
            <Field label="合同英文名称（必填）">
              <input
                name="nameEn"
                required
                maxLength={255}
                defaultValue={party?.nameEn}
                placeholder="填写合同使用的英文公司全称"
                aria-invalid={!!fieldErrors.nameEn || undefined}
                aria-describedby={describedBy("nameEn")}
              />
              {fieldError("nameEn")}
            </Field>
          </div>
          <Field label="合同中文名称（选填）">
            <input
              name="nameCn"
              maxLength={255}
              defaultValue={party?.nameCn}
              placeholder="填写中文公司名称"
              aria-invalid={!!fieldErrors.nameCn || undefined}
              aria-describedby={describedBy("nameCn")}
            />
            {fieldError("nameCn")}
          </Field>
          <Field label="电话（选填）">
            <input
              name="phone"
              type="tel"
              maxLength={100}
              defaultValue={party?.phone}
              placeholder="可填写国家或地区区号"
              aria-invalid={!!fieldErrors.phone || undefined}
              aria-describedby={describedBy("phone")}
            />
            {fieldError("phone")}
          </Field>
          <div className="settlement-party-dialog__wide">
            <Field label="英文地址（必填）">
              <textarea
                name="addressEn"
                required
                maxLength={500}
                rows={2}
                defaultValue={party?.addressEn}
                placeholder="填写合同使用的完整英文地址"
                aria-invalid={!!fieldErrors.addressEn || undefined}
                aria-describedby={describedBy("addressEn")}
              />
              {fieldError("addressEn")}
            </Field>
          </div>
          <div className="settlement-party-dialog__wide">
            <Field label="中文地址（选填）">
              <textarea
                name="addressCn"
                maxLength={500}
                rows={2}
                defaultValue={party?.addressCn}
                placeholder="填写中文地址"
                aria-invalid={!!fieldErrors.addressCn || undefined}
                aria-describedby={describedBy("addressCn")}
              />
              {fieldError("addressCn")}
            </Field>
          </div>
        </fieldset>
        {error && (
          <div className="settlement-party-dialog__feedback">
            <Alert tone="danger" title="未保存，填写内容已保留">
              {error}
            </Alert>
          </div>
        )}
        <div className="settlement-party-dialog__actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "正在保存…" : "保存抬头"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
