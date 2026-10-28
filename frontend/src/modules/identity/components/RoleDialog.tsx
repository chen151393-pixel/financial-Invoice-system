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
  enabled,
  onSave,
  onClose,
}: {
  title: string;
  description: string;
  roles: RoleItem[];
  initial: string[];
  /** 传入时显示“角色来源”选择（个人角色） */
  customRoles?: boolean;
  enabled?: boolean;
  onSave: (roles: string[], customRoles: boolean, enabled: boolean) => Promise<void>;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(new Set(initial));
  const [custom, setCustom] = useState(customRoles ?? false);
  const [enable, setEnable] = useState(enabled ?? false);
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
        enable,
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
        <Alert>
          角色当前用于登录资格和人员管理权限；财务、采购等业务操作的细分权限尚未接入，“只读”角色暂不能限制所有业务写操作。
        </Alert>
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
        {enabled !== undefined && (
          <fieldset>
            <legend>平台访问</legend>
            <label>
              <input
                type="checkbox"
                checked={enable}
                disabled={busy}
                onChange={(event) => setEnable(event.target.checked)}
              />
              启用此成员
            </label>
            <p>启用需要在职、处于同步范围内且有生效角色；关闭后现有会话立即失效。</p>
          </fieldset>
        )}
        {selected.has("admin") && (
          <Alert tone="warning">系统管理员可以修改所有人员的角色、启用状态和同步范围，请确认授权对象。</Alert>
        )}
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
            {busy ? "保存中…" : enabled !== undefined ? "保存角色与启用状态" : "保存角色"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
