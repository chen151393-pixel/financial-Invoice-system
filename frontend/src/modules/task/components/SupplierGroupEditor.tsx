import { useEffect, useId, useRef, useState } from "react";
import { Alert, Badge, Button, Dialog, Field } from "../../../shared/components/ui";
import type {
  GroupFields,
  GroupSave,
  SupplierOption,
  WecomGroupPage,
  SupplierGroupMatchQuery,
} from "../types/supplier-group";
import { WecomGroupPicker } from "./WecomGroupPicker";
import "./supplier-group-editor.css";

export function SupplierGroupEditor({
  initial,
  searchWecom,
  save: submit,
  onSaved,
  onClose,
}: {
  initial: SupplierOption & { nsInternalId?: string };
  searchWecom: (query: SupplierGroupMatchQuery) => Promise<WecomGroupPage>;
  save: (value: GroupSave) => Promise<unknown>;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [group, setGroup] = useState<GroupFields | null>(initial.binding ?? null);
  const binding = initial.binding;
  const [enabled, setEnabled] = useState(binding?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const groupInput = useRef<HTMLInputElement>(null);
  const formId = useId();
  useEffect(() => {
    groupInput.current?.focus();
  }, []);
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await submit({
        supplierId: initial.supplierId,
        chatId: group?.chatId ?? "",
        enabled,
        revision: binding?.revision ?? 0,
      });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败，请重新查询配置");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="维护供应商档案" onClose={onClose} busy={busy} className="sg-editor-dialog">
      <div className="sg-editor-supplier">
        <div>
          <strong>{initial.supplierName}</strong>
          <p>
            NS 账套：{initial.account} · {initial.nsInternalId ? "NS 供应商 ID" : "供应商 ID"}：
            {initial.nsInternalId || initial.supplierId}
          </p>
        </div>
        <Badge tone={binding ? "info" : "warning"}>{binding ? "已有群绑定" : "尚未绑定群"}</Badge>
      </div>
      <div className="sg-editor-layout">
        <WecomGroupPicker
          supplier={initial}
          selectedId={group?.chatId}
          search={searchWecom}
          onChoose={setGroup}
          disabled={busy}
          inputRef={groupInput}
        />
        <aside className="sg-editor-binding" aria-label="默认通知群设置">
          <h4>默认通知群</h4>
          {group ? (
            <div className="sg-editor-chosen" aria-live="polite">
              <Badge tone="success" dot={false}>
                已选择
              </Badge>
              <strong>{group.groupName}</strong>
              <p>
                群主：{group.employee}（{group.userid}）
              </p>
              <details>
                <summary>查看群标识</summary>
                <p>外部群 ID：{group.chatId}</p>
                <p>群主 ID：{group.userid}</p>
              </details>
            </div>
          ) : (
            <div className="sg-editor-no-group">
              <strong>尚未选择外部群</strong>
              <p>查找并选择一个群，作为该供应商的默认通知群。</p>
            </div>
          )}
          <form
            id={formId}
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <Field label="绑定状态">
              <select
                value={enabled ? "enabled" : "disabled"}
                disabled={busy}
                onChange={(event) => setEnabled(event.target.value === "enabled")}
              >
                <option value="enabled">启用</option>
                <option value="disabled">停用</option>
              </select>
            </Field>
          </form>
          <p className="sg-editor-help">
            {binding
              ? "保存将更新当前绑定；停用后保留已存群信息。"
              : "每个供应商保留一个默认通知群，群主信息随选择自动带入。"}
          </p>
        </aside>
      </div>
      {error && (
        <Alert tone="danger" title="档案保存失败">
          {error}
        </Alert>
      )}
      <footer className="sg-editor-footer">
        <p>保存时核验群与群主，仅维护绑定，不会发送消息。</p>
        <div>
          <Button disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button form={formId} type="submit" variant="primary" disabled={busy}>
            {busy ? "保存中…" : "保存配置"}
          </Button>
        </div>
      </footer>
    </Dialog>
  );
}
