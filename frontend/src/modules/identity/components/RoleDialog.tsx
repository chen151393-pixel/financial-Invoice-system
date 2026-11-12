import { useRef, useState } from "react";
import { Alert, Button, Dialog } from "../../../shared/components/ui";
import type { RoleItem } from "../types";

/** 部门默认角色编辑；个人角色与启用状态由成员编辑区维护。 */
export function RoleDialog({
  title,
  description,
  roles,
  initial,
  onSave,
  onClose,
}: {
  title: string;
  description: string;
  roles: RoleItem[];
  initial: string[];
  onSave: (roles: string[]) => Promise<void>;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(new Set(initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);

  function toggle(code: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function save() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await onSave(roles.map((role) => role.code).filter((code) => selected.has(code)));
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存失败");
      setBusy(false);
    } finally {
      submitting.current = false;
    }
  }

  return (
    <Dialog title={title} busy={busy} onClose={onClose}>
      <div className="identity-role-dialog">
        <p>{description}</p>
        <Alert>
          角色决定可访问的页面，多角色取并集。页面内操作仍按现有规则校验，“只读”角色尚不能限制所有业务写操作。
        </Alert>
        <fieldset>
          <legend>部门默认角色</legend>
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
            {busy ? "保存中…" : "保存部门角色"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
