import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { useDialog } from "../hooks/useDialog";
import type { BatchApproveResult, ComparisonGroup } from "../types";

/** 批量审核确认：列出当前页已选的报关单；提交后逐张展示后端结果（通过 / 跳过及原因）。 */
export function BatchApproveDialog({
  groups,
  busy,
  error,
  result,
  onClose,
  onApprove,
}: {
  groups: ComparisonGroup[];
  busy: boolean;
  error: string;
  result: BatchApproveResult | null;
  onClose: () => void;
  onApprove: (note: string) => void;
}) {
  const ref = useDialog();
  const [note, setNote] = useState("");
  const names = new Map(groups.map((group) => [group.id, group.recordNumber]));
  return (
    <dialog
      ref={ref}
      className="fr-dialog fr-dialog--group"
      aria-labelledby="finance-batch-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <header>
        <div>
          <h2 id="finance-batch-title">{result ? "批量审核结果" : "批量审核通过"}</h2>
          <p>当前页已选 {groups.length} 张报关单</p>
        </div>
        <button className="fr-close" disabled={busy} onClick={onClose} aria-label="关闭批量审核窗口">
          ×
        </button>
      </header>
      <div className="fr-dialog__body">
        {result ? (
          <>
            <p className="fr-status-note" role="status">
              {result.approved.length} 张已审核通过并生成开票任务
              {result.skipped.length ? `，${result.skipped.length} 张未通过` : ""}。
            </p>
            {result.skipped.length > 0 && (
              <ul className="fr-batch-list">
                {result.skipped.map((item) => (
                  <li key={item.id}>
                    <strong>{names.get(item.id) ?? item.id}</strong>
                    <span className="fr-error">{item.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <>
            <p className="fr-dialog__hint">
              仅审核下列当前页已勾选的报关单，不包含其他页或未勾选的报关单。后端逐张重新核对来源，来源已变化的会被跳过并列出原因；需要补充结算币种证据的报关单请单张审核。
            </p>
            <ul className="fr-batch-list">
              {groups.map((group) => (
                <li key={group.id}>
                  <strong>{group.recordNumber}</strong>
                  <span>
                    {group.declaration || "未填写"} · {group.customsCount} 条报关行 · {group.purchaseCount}{" "}
                    条子采购行
                  </span>
                </li>
              ))}
            </ul>
            <label className="fr-note-label" htmlFor="finance-batch-note">
              审核备注 <span>选填，应用于本次全部报关单</span>
              <textarea
                id="finance-batch-note"
                disabled={busy}
                rows={3}
                maxLength={300}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
          </>
        )}
        {error && (
          <p className="fr-error" role="alert">
            {error}
          </p>
        )}
        {busy && <p role="status">正在逐张保存审核结果，请稍候…</p>}
      </div>
      <footer>
        <Button disabled={busy} onClick={onClose}>
          {result ? "关闭" : "取消"}
        </Button>
        {!result && (
          <Button variant="primary" disabled={busy || !groups.length} onClick={() => onApprove(note)}>
            {busy ? "保存中…" : `审核通过 ${groups.length} 张`}
          </Button>
        )}
      </footer>
    </dialog>
  );
}
