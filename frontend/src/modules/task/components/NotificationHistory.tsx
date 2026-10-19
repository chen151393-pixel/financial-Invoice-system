import type { NotificationEvent } from "../types/task";
import { formatTime } from "./format";

export function NotificationHistory({ history }: { history: NotificationEvent[] }) {
  return (
    <section className="itn-history" aria-label="通知记录">
      <h3>通知记录</h3>
      {history.length === 0 ? (
        <p className="it-help">暂无保存或发送记录。</p>
      ) : (
        history.map((event) => (
          <details key={event.revision}>
            <summary>
              {event.sentAt ? (event.channel === "wecom" ? "企微渠道已发送" : "人工登记已发送") : "保存通知"}{" "}
              · {formatTime(event.at)} · 版本 {event.revision}
            </summary>
            <dl className="itn-facts itn-record-facts">
              <dt>保存人</dt>
              <dd>{event.actor}</dd>
              <dt>外部群</dt>
              <dd>{event.groupName || "未填写"}</dd>
              <dt>发送员工</dt>
              <dd>{event.employee || "未填写"}</dd>
              {event.sentAt && (
                <>
                  <dt>发送时间</dt>
                  <dd>
                    {formatTime(event.sentAt)}（{event.channel === "wecom" ? "渠道回执" : "人工填写"}）
                  </dd>
                  <dt>登记人</dt>
                  <dd>{event.recordedBy}</dd>
                  <dt>登记说明</dt>
                  <dd>{event.note}</dd>
                  <dt>合同</dt>
                  <dd>
                    {event.attachments.map((filename, index) => (
                      <div key={index}>{filename}</div>
                    ))}
                  </dd>
                </>
              )}
            </dl>
            {event.sentAt && (
              <p className="it-help">
                {event.channel === "wecom"
                  ? "企微已确认目标群发送，不代表供应商已读或已开票。"
                  : "此记录为人工登记，不代表企微回执、供应商已读或已开票。"}
              </p>
            )}
            <pre>{event.message}</pre>
          </details>
        ))
      )}
    </section>
  );
}
