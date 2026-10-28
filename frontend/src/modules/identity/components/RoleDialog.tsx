import { useState } from "react";
import { Alert, Button, Dialog } from "../../../shared/components/ui";
import type { RoleItem } from "../types";

/** 选择角色并保存；角色是否有效、保存是否允许都由后端校验。 */
export function RoleDialog({
  title,
  description,
  roles,
  initial,
  customRoles,
  onSave,
  onClose,
}: {
  title: string;
  description: string;
  roles: RoleItem[];
  initial: string[];
  /** 传入时显示“角色来源”选择（个人角色） */
  customRoles?: boolean;
  onSave: (roles: string[], customRoles: boolean) => Promise<void>;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(new Set(initial));
  const [custom, setCustom] = useState(customRoles ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function toggle(code: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await onSave(
        roles.map((role) => role.code).filter((code) => selected.has(code)),
        custom,
      );
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存失败");
      setBusy(false);
    }
  }

  return (
    <Dialog title={title} busy={busy} onClose={onClose}>
      <div className="identity-role-dialog">
        <p>{description}</p>
        {customRoles !== undefined && (
          <fieldset>
            <legend>角色来源</legend>
            <label>
              <input type="radio" checked={!custom} disabled={busy} onChange={() => setCustom(false)} />
              部门默认角色，再加上以下个人角色
            </label>
            <label>
              <input type="radio" checked={custom} disabled={busy} onChange={() => setCustom(true)} />
              只按以下角色（不使用部门默认角色）
            </label>
          </fieldset>
        )}
        <fieldset>
          <legend>{customRoles !== undefined ? "个人角色" : "默认角色"}</legend>
          {roles.map((role) => (
            <label key={role.code}>
              <input
                type="checkbox"
                checked={selected.has(role.code)}
                disabled={busy}
                onChange={() => toggle(role.code)}
              />
              {role.label}
            </label>
          ))}
        </fieldset>
        {error && (
          <Alert tone="danger" title="未保存">
            {error}
          </Alert>
        )}
        <div className="identity-role-dialog__actions">
          <Button disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            {busy ? "保存中…" : "保存角色"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
