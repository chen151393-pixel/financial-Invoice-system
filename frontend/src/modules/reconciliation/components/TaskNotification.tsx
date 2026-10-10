import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../../../shared/components/Button";
import { recordTaskNotification, saveTaskNotification } from "../api";
import type { InvoiceTaskDetail } from "../task-types";
import "./task-notification.css";

function NotificationDialog({
  title,
  onClose,
  children,
  busy = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
}) {
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
  return (
    <dialog
      ref={ref}
      className="itn-dialog"
      aria-labelledby="itn-dialog-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <header>
        <h3 id="itn-dialog-title">{title}</h3>
        <Button disabled={busy} onClick={onClose}>
          关闭
        </Button>
      </header>
      {children}
    </dialog>
  );
}

export function TaskNotification({
  detail,
  onUpdate,
}: {
  detail: InvoiceTaskDetail;
  onUpdate: (detail: InvoiceTaskDetail) => void;
}) {
  const notification = detail.notification;
  const [draft, setDraft] = useState({
    groupName: notification.groupName,
    employee: notification.employee,
    message: notification.message,
  });
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);
  const [dialog, setDialog] = useState<"preview" | "record" | null>(null);
  const [sentAt, setSentAt] = useState("");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const dirty =
    draft.groupName !== notification.groupName ||
    draft.employee !== notification.employee ||
    draft.message !== notification.message;
  const readonly = !notification.edit.allowed;

  async function save(record = false) {
    if (busy) return;
    setBusy(true);
    setFeedback(null);
    try {
      const updated = record
        ? await recordTaskNotification(detail.task.id, {
            revision: notification.revision,
            sentAt: sentAt ? new Date(sentAt).toISOString() : "",
            note,
            confirmed,
          })
        : await saveTaskNotification(detail.task.id, { ...draft, revision: notification.revision });
      setDialog(null);
      onUpdate(updated);
    } catch (error) {
      setFeedback({
        error: true,
        text: error instanceof Error ? error.message : "保存失败，请刷新核实最新记录",
      });
    } finally {
      setBusy(false);
    }
  }
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
  return (
    <div className="itn">
      <header className="itn-heading">
        <div>
          <h3>{notification.statusLabel}</h3>
          <p className="it-help">通知渠道：企微外部群 · 人工发送与登记</p>
        </div>
        <Button
          onClick={() => {
            setFeedback(null);
            setDialog("preview");
          }}
        >
          预览通知
        </Button>
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
          <Link to={paths.supplierGroups}>维护供应商群配置</Link>
          <p className="it-help">
            以下为本任务接收信息。已保存的通知保留原内容，默认群配置不会覆盖历史记录。
          </p>
          <dl className="itn-facts">
            <dt>供应商</dt>
            <dd>{detail.task.supplier}</dd>
            <dt>采购公司</dt>
            <dd>{detail.task.company || "以合同为准"}</dd>
          </dl>
          <label className="itn-field">
            企微外部群名称
            <input
              value={draft.groupName}
              disabled={readonly || busy}
              maxLength={200}
              placeholder="填写供应商所在的企微外部群"
              onChange={(e) => setDraft({ ...draft, groupName: e.target.value })}
            />
          </label>
          <label className="itn-field">
            负责发送的员工
            <input
              value={draft.employee}
              disabled={readonly || busy}
              maxLength={100}
              placeholder="填写实际发送通知的员工"
              onChange={(e) => setDraft({ ...draft, employee: e.target.value })}
            />
          </label>
          <p className="it-help">发送方式：员工将正文和合同发至外部群，实际发送后在此登记。</p>
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
          <p className="it-help">请从共享盘添加文件；通知正文不包含内部共享盘路径。</p>
        </section>
      </div>
      <div className="itn-actions">
        <Button variant="primary" disabled={readonly || busy} onClick={() => void save()}>
          {busy ? "保存中…" : "保存通知"}
        </Button>
        <Button disabled={busy} onClick={() => void copy()}>
          复制通知正文
        </Button>
        <Button
          disabled={!notification.record.allowed || dirty || busy}
          onClick={() => {
            setFeedback(null);
            setDialog("record");
          }}
        >
          登记已人工发送
        </Button>
        <Button disabled title={notification.send.reason}>
          企微自动发送（未接入）
        </Button>
      </div>
      <p className="it-help">{dirty ? "请先保存修改后的通知，再登记发送。" : notification.record.reason}</p>
      <section className="itn-history" aria-label="通知记录">
        <h3>通知记录</h3>
        {notification.history.length === 0 ? (
          <p className="it-help">暂无保存或发送记录。</p>
        ) : (
          notification.history.map((event) => (
            <details key={event.revision}>
              <summary>
                {event.sentAt ? "人工登记已发送" : "保存通知"} · {new Date(event.at).toLocaleString("zh-CN")}{" "}
                · 版本 {event.revision}
              </summary>
              <p>操作人：{event.actor}</p>
              <p>
                外部群：{event.groupName || "未填写"} · 发送员工：{event.employee || "未填写"}
              </p>
              {event.sentAt && (
                <>
                  <p>实际发送时间（人工填写）：{new Date(event.sentAt).toLocaleString("zh-CN")}</p>
                  <p>登记说明：{event.note}</p>
                  <p>合同：{event.attachments.join("、")}</p>
                  <p>此记录为人工登记，不代表企微回执、供应商已读或已开票。</p>
                </>
              )}
              <pre>{event.message}</pre>
            </details>
          ))
        )}
      </section>
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
              <p className="it-help">仅预览正文，未向供应商发送。</p>
              <Button onClick={() => void copy()}>复制正文</Button>
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void save(true);
              }}
            >
              <p className="it-help">
                请在企微外部群实际发送正文及合同后登记。登记后保存内容快照，任务进入等待收票。
              </p>
              <label className="itn-field">
                实际发送时间
                <input
                  type="datetime-local"
                  value={sentAt}
                  disabled={busy}
                  onChange={(e) => setSentAt(e.target.value)}
                />
              </label>
              <label className="itn-field">
                登记说明
                <textarea
                  rows={3}
                  maxLength={500}
                  value={note}
                  disabled={busy}
                  placeholder="例如：已核对外部群并发送正文及合同"
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <label className="itn-check">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                我确认已在上述外部群发送本次通知及合同
              </label>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "登记中…" : "保存发送登记"}
              </Button>
            </form>
          )}
        </NotificationDialog>
      )}
    </div>
  );
}
