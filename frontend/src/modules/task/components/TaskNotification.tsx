import { useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import type { NotificationDraft, NotificationRecord, TaskDetail } from "../types/task";
import type { DeliveryController } from "../types/delivery";
import { WecomNotification } from "./WecomNotification";
import { NotificationDialog } from "./NotificationDialog";
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
    try {
      await navigator.clipboard.writeText(draft.message);
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
  const field = (key: "groupName" | "employee", label: string, max: number, placeholder: string) => (
    <label className="itn-field">
      {label}
      <input
        value={draft[key]}
        disabled={readonly || busy}
        maxLength={max}
        placeholder={placeholder}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
      />
    </label>
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
      <p className="it-help">{notification.send.reason}</p>
      {!dialog && feedbackNode}
      <div className="itn-columns">
        <section aria-label="接收信息">
          <h3>接收信息</h3>
          <p className="it-help">{notification.groupConfigReason}</p>
          {notification.supplierGroup && (
            <dl className="itn-facts">
              <dt>默认通知群</dt>
              <dd>{notification.supplierGroup.groupName}</dd>
              <dt>外部群 ID</dt>
              <dd>{notification.supplierGroup.chatId}</dd>
              <dt>群主</dt>
              <dd>
                {notification.supplierGroup.employee} · {notification.supplierGroup.userid}
              </dd>
            </dl>
          )}
          <Link to={paths.supplierGroups}>维护供应商档案</Link>
          <dl className="itn-facts">
            <dt>供应商</dt>
            <dd>{detail.task.supplier}</dd>
            <dt>采购公司</dt>
            <dd>{detail.task.company}</dd>
          </dl>
          {field("groupName", "人工发送群名称", 200, "仅用于人工发送登记")}
          {field("employee", "人工发送员工", 100, "仅用于人工发送登记")}
          <p className="it-help">已保存的通知保留原内容，默认群配置变化不会覆盖历史记录。</p>
          <p className="it-help">{notification.edit.reason}</p>
        </section>
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
          <label className="itn-field">
            通知正文
            <textarea
              rows={11}
              value={draft.message}
              readOnly={readonly}
              disabled={busy}
              maxLength={4000}
              onChange={(e) => setDraft({ ...draft, message: e.target.value })}
            />
          </label>
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
      <div className="itn-actions">
        <Button variant="primary" disabled={readonly || busy} onClick={() => void save()}>
          {busy ? "保存中…" : "保存通知"}
        </Button>
        <Button disabled={busy} onClick={() => void copy()}>
          复制通知正文
        </Button>
        <Button disabled={!notification.record.allowed || dirty || busy} onClick={() => setDialog("record")}>
          登记已人工发送
        </Button>
      </div>
      <p className="it-help">{dirty ? "请先保存修改后的通知，再登记发送。" : notification.record.reason}</p>
      <WecomNotification controller={delivery} notification={notification} dirty={dirty} disabled={saving} />
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
