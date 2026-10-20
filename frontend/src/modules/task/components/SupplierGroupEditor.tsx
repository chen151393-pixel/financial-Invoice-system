import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type {
  GroupFields,
  GroupSave,
  SupplierOption,
  WecomGroupPage,
  SupplierGroupMatchQuery,
} from "../types/supplier-group";
import { WecomGroupPicker } from "./WecomGroupPicker";

export function SupplierGroupEditor({
  initial,
  searchWecom,
  save: submit,
  onSaved,
  onClose,
}: {
  initial: SupplierOption;
  searchWecom: (query: SupplierGroupMatchQuery) => Promise<WecomGroupPage>;
  save: (value: GroupSave) => Promise<unknown>;
  onSaved: () => void;
  onClose: () => void;
}) {
  const supplier = initial;
  const [group, setGroup] = useState<GroupFields | null>(initial.binding ?? null);
  const binding = initial.binding;
  const [enabled, setEnabled] = useState(initial.binding?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const groupInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await submit({
        supplierId: supplier?.supplierId ?? "",
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
    <section className="sg-editor" aria-labelledby="sg-editor-title">
      <div className="sg-row sg-between">
        <h2 id="sg-editor-title" ref={heading} tabIndex={-1}>
          维护供应商档案
        </h2>
        <Button disabled={busy} onClick={onClose}>
          取消
        </Button>
      </div>
      <p className="it-help">查找外部群后核对选择，群主信息自动带入。每个供应商保留一个默认通知群。</p>
      {supplier && (
        <p className="sg-selection">
          <strong>{supplier.supplierName}</strong> · {supplier.account} · 供应商 ID：{supplier.supplierId}
        </p>
      )}
      {binding && (
        <p className="it-help">
          已有绑定：{binding.groupName}（{binding.enabled ? "启用" : "停用"}
          ）。保存将更新此配置，不会新增重复绑定。
        </p>
      )}
      {supplier ? (
        <WecomGroupPicker
          key={supplier.supplierId}
          supplier={supplier}
          selectedId={group?.chatId}
          search={searchWecom}
          onChoose={setGroup}
          disabled={busy}
          inputRef={groupInput}
        />
      ) : (
        <p className="it-help">选择供应商后，可点击“查找外部群”查询。</p>
      )}
      {group && (
        <div className="sg-selection">
          <p>
            <strong>已选择：{group.groupName}</strong>
          </p>
          <p>
            群主：{group.employee} · {group.userid}
          </p>
          <details>
            <summary>查看群标识（自动获取）</summary>
            <p>外部群 ID：{group.chatId}</p>
            <p>群主 ID：{group.userid}</p>
          </details>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div className="sg-fields">
          <label>
            配置状态
            <select
              value={enabled ? "enabled" : "disabled"}
              disabled={busy}
              onChange={(e) => setEnabled(e.target.value === "enabled")}
            >
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </select>
          </label>
        </div>
        {error && (
          <p role="alert" className="sg-feedback">
            {error}
          </p>
        )}
        <div className="sg-row">
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "保存中…" : "保存配置"}
          </Button>
          <span className="it-help">
            保存时重新核验企微群及群主；仅停用原群时保留已存信息。此操作不会发送消息。
          </span>
        </div>
      </form>
    </section>
  );
}
