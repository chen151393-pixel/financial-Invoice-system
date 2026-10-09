import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import {
  querySuppliers,
  saveSupplierGroup,
  type GroupBinding,
  type GroupFields,
  type SupplierOption,
} from "../group-api";
import { GroupLookup } from "./GroupLookup";
import { WecomGroupPicker } from "./WecomGroupPicker";

export function SupplierGroupEditor({
  initial,
  onSaved,
  onClose,
}: {
  initial: GroupBinding | null;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [supplier, setSupplier] = useState<SupplierOption | null>(initial);
  const [group, setGroup] = useState<GroupFields | null>(initial);
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const groupInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  async function save() {
    setBusy(true);
    setError("");
    try {
      await saveSupplierGroup({
        account: supplier?.account ?? "",
        supplierId: supplier?.supplierId ?? "",
        chatId: group?.chatId ?? "",
        enabled,
        revision: initial?.revision ?? 0,
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
          {initial ? "修改供应商群配置" : "新增供应商群配置"}
        </h2>
        <Button disabled={busy} onClick={onClose}>
          取消
        </Button>
      </div>
      <p className="it-help">
        每个供应商在同一 NS 环境配置一个默认通知群。查询并选择企微群，系统自动获取群及群主信息。
      </p>
      {supplier && (
        <p className="sg-selection">
          <strong>{supplier.supplierName}</strong> · {supplier.account} · 供应商 ID：{supplier.supplierId}
        </p>
      )}
      {!initial && (
        <details open={!supplier}>
          <summary>选择供应商</summary>
          <GroupLookup
            label="查询系统供应商"
            load={querySuppliers}
            disabled={busy}
            render={(item) => (
              <>
                {item.supplierName}
                <small>
                  {item.account} · {item.supplierId}
                </small>
              </>
            )}
            onChoose={(item) => {
              setSupplier(item);
              groupInput.current?.focus();
            }}
          />
        </details>
      )}
      <WecomGroupPicker onChoose={setGroup} disabled={busy} inputRef={groupInput} />
      {group && (
        <div className="sg-selection">
          <p>
            <strong>已选择：{group.groupName}</strong>
          </p>
          <p>群主：{group.employee}</p>
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
