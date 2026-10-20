import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { WritebackRequest } from "../types";
import "../writeback-dialog.css";

/** 打开即进入模态并聚焦弹窗；关闭后焦点回到触发按钮。 */
function useModal() {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);
  return ref;
}

/** 确认回写：展示写入对象和不可撤销的后果，勾选核对后才能提交；是否允许执行仍由后端重新校验。 */
export function ConfirmDialog({
  data,
  busy,
  onCancel,
  onConfirm,
}: {
  data: WritebackRequest;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useModal();
  const [checked, setChecked] = useState(false);
  return (
    <dialog
      ref={ref}
      className="wb-dialog"
      aria-labelledby="wb-confirm-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <header className="wb-dialog__head">
        <h2 id="wb-confirm-title">确认回写到 NetSuite</h2>
        <button
          type="button"
          className="wb-dialog__close"
          disabled={busy}
          onClick={onCancel}
          aria-label="关闭确认窗口"
        >
          ×
        </button>
      </header>
      <div className="wb-dialog__body">
        <dl className="wb-dialog__facts">
          <dt>写入账套</dt>
          <dd className="wb-strong">{data.account}</dd>
          <dt>发票</dt>
          <dd>
            <span className="wb-mono">{data.invoiceNo}</span> · {data.invoiceDate} · {data.vendorName}
          </dd>
          <dt>本次实收</dt>
          <dd className="wb-mono wb-strong">
            {data.totalAmount} {data.currency}
          </dd>
        </dl>
        <div className="wb-dialog__ops">
          <span className="wb-muted">将在 NS 中执行</span>
          <ul>
            {data.operations.map((operation) => (
              <li key={operation}>{operation}</li>
            ))}
          </ul>
        </div>
        <div className="wb-dialog__warning" role="note">
          <strong>写入后不能在本系统撤销</strong>
          <span>
            如需冲回，须在 NS 中人工处理。若 NS 响应超时，结果将标为“待核实”，相关账单会被锁定，不能重复提交。
          </span>
        </div>
        <label className="wb-dialog__check">
          <input
            type="checkbox"
            checked={checked}
            disabled={busy}
            onChange={(event) => setChecked(event.target.checked)}
          />
          我已核对以上明细与金额
        </label>
      </div>
      <footer className="wb-dialog__actions">
        <Button disabled={busy} onClick={onCancel}>
          取消
        </Button>
        <Button variant="primary" disabled={busy || !checked} onClick={onConfirm}>
          {busy ? "正在提交…" : "确认回写"}
        </Button>
      </footer>
    </dialog>
  );
}
