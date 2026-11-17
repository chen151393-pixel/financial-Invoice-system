import { useState } from "react";
import { Alert, Button, Dialog } from "../../../shared/components/ui";
import { saveParty } from "../api";
import type { Party } from "../types";

/** 新增或修改合同抬头；重名等校验由后端返回。 */
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

  async function submit(form: HTMLFormElement) {
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    setBusy(true);
    setError("");
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
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title={party ? "修改合同抬头" : "新增合同抬头"} onClose={onClose} busy={busy}>
      <form
        className="settlement-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(event.currentTarget);
        }}
      >
        <label className="settlement-form__wide">
          匹配名称（买方须与海关回执的境外收货人完全一致；卖方填境内发货人名称）
          <input name="name" required maxLength={300} defaultValue={party?.name} />
        </label>
        <label>
          合同英文名称
          <input name="nameEn" required maxLength={255} defaultValue={party?.nameEn} />
        </label>
        <label>
          合同中文名称
          <input name="nameCn" maxLength={255} defaultValue={party?.nameCn} />
        </label>
        <label className="settlement-form__wide">
          英文地址
          <input name="addressEn" required maxLength={500} defaultValue={party?.addressEn} />
        </label>
        <label className="settlement-form__wide">
          中文地址
          <input name="addressCn" maxLength={500} defaultValue={party?.addressCn} />
        </label>
        <label>
          电话
          <input name="phone" maxLength={100} defaultValue={party?.phone} />
        </label>
        {error && (
          <Alert tone="danger" title="未保存">
            {error}
          </Alert>
        )}
        <div className="settlement-form__actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "正在保存…" : "保存"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
