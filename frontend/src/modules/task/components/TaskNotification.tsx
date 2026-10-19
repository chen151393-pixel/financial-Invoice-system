import { useId, useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { NotificationDraft, NotificationRecord, TaskDetail } from "../types/task";
import type { DeliveryController } from "../types/delivery";
import { WecomNotification } from "./WecomNotification";
import { NotificationCopyButton } from "./NotificationCopyButton";
import { NotificationDialog } from "./NotificationDialog";
import { NotificationRecipients } from "./NotificationRecipients";
import { NotificationHistory } from "./NotificationHistory";
import { NotificationRecordForm, type RecordInput } from "./NotificationRecordForm";
import "./task-notification.css";

type Feedback = { error: boolean; text: string } | null;

export function TaskNotification({
  detail,
  onSave,
  onRecord,
  delivery,
}: {
  detail: TaskDetail;
  onSave: (draft: NotificationDraft) => Promise<void>;
  onRecord: (record: NotificationRecord) => Promise<void>;
  delivery: DeliveryController;
}) {
  const notification = detail.notification;
  const messageId = useId();
  const [copiedMessage, setCopiedMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    groupName: notification.groupName,
    employee: notification.employee,
    message: notification.message,
  });
  const [saving, setBusy] = useState(false);
  const busy = saving || delivery.busy;
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [dialog, setDialog] = useState<"preview" | "record" | null>(null);
  const dirty =
    draft.groupName !== notification.groupName ||
    draft.employee !== notification.employee ||
    draft.message !== notification.message;
  const readonly = !notification.edit.allowed;
  const copied = copiedMessage === draft.message;

  async function submit(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setFeedback(null);
    try {
      await action();
      setDialog(null);
    } catch (error) {
      setFeedback({
        error: true,
        text: error instanceof Error ? error.message : "保存失败，请刷新核实最新记录",
      });
    } finally {
      setBusy(false);
    }
  }
  const save = () => submit(() => onSave({ ...draft, revision: notification.revision }));
  const record = (value: RecordInput) =>
    submit(() => onRecord({ ...value, revision: notification.revision }));
  async function copy() {
    setCopiedMessage(null);
    try {
      await navigator.clipboard.writeText(draft.message);
      setCopiedMessage(draft.message);
      setFeedback({ error: false, text: "通知正文已复制，请在企微外部群粘贴，并从共享盘添加对应合同。" });
    } catch {
      setFeedback({ error: true, text: "复制失败，请选中通知正文手动复制。" });
    }
  }
  const feedbackNode = feedback && (
    <p className="itd-feedback" role={feedback.error ? "alert" : "status"}>
      {feedback.text}
    </p>
  );
  return (
    <div className="itn">
      <header className="itn-heading">
        <div>
          <h3>{notification.statusLabel}</h3>
          <p className="it-help">通知渠道：企微群发或人工发送登记</p>
        </div>
        <Button onClick={() => setDialog("preview")}>预览通知</Button>
      </header>
      {!dialog && feedbackNode}
      <div className="itn-columns">
        <NotificationRecipients
          detail={detail}
          draft={draft}
          disabled={readonly || busy}
          onChange={setDraft}
        />
        <section aria-label="本次通知">
          <div className="itn-heading">
            <h3>本次通知</h3>
            <Button
              disabled={readonly || busy}
              onClick={() => setDraft({ ...draft, message: notification.defaultMessage })}
            >
              恢复默认内容
            </Button>
          </div>
          <div className="itn-field">
            <label htmlFor={messageId}>通知正文</label>
            <div className="task-notification-message">
              <textarea
                id={messageId}
                rows={11}
                value={draft.message}
                readOnly={readonly}
                disabled={busy}
                maxLength={4000}
                onChange={(e) => setDraft({ ...draft, message: e.target.value })}
              />
              <NotificationCopyButton copied={copied} disabled={busy} onCopy={() => void copy()} />
            </div>
          </div>
          <p className="it-help">
            系统根据审核任务生成默认内容，支持发送前手动编辑。
            {dirty
              ? "有未保存的修改。"
              : notification.revision
                ? "当前内容已保存。"
                : "当前为默认内容，尚未保存。"}
          </p>
          <div className="itn-files">
            <h3>发送时附上合同</h3>
            {detail.documents.map((doc) => (
              <div key={doc.orderId}>
                <strong>{doc.filename || doc.orderNumber}</strong>
                <p className="it-help">{doc.archivePath || doc.prepare.reason}</p>
              </div>
            ))}
          </div>
          <p className="it-help">企微群发由系统上传合同；人工发送时请从共享盘添加。正文不包含内部路径。</p>
        </section>
      </div>
      <div className="itn-actions" role="group" aria-label="通知操作">
        <Button disabled={readonly || busy} onClick={() => void save()}>
          {saving ? "保存中…" : "保存通知"}
        </Button>
        <Button disabled={!notification.record.allowed || dirty || busy} onClick={() => setDialog("record")}>
          登记已人工发送
        </Button>
        <Button
          variant="primary"
          disabled={busy || dirty || !notification.send.allowed}
          onClick={() =>
            void delivery.prepare(notification.revision, notification.supplierGroup?.revision ?? 0)
          }
        >
          提交企微群发
        </Button>
      </div>
      <p className="it-help">{dirty ? "请先保存修改后的通知，再登记发送。" : notification.record.reason}</p>
      <p className="it-help">{dirty ? "请先保存通知，再预览提交。" : notification.send.reason}</p>
      <WecomNotification controller={delivery} />
      <NotificationHistory history={notification.history} />
      {dialog && (
        <NotificationDialog
          title={dialog === "preview" ? "供应商开票通知预览" : "登记已人工发送"}
          busy={busy}
          onClose={() => setDialog(null)}
        >
          {feedbackNode}
          <p>企微外部群：{draft.groupName || "未填写"}</p>
          <p>发送员工：{draft.employee || "未填写"}</p>
          {dialog === "preview" ? (
            <>
              <pre>{draft.message}</pre>
              <p className="it-help">此窗口仅预览正文，不触发发送。</p>
              <Button onClick={() => void copy()}>复制正文</Button>
            </>
          ) : (
            <NotificationRecordForm busy={busy} onSubmit={(value) => void record(value)} />
          )}
        </NotificationDialog>
      )}
    </div>
  );
}
