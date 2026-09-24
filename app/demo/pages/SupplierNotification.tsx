import { useRef, useState } from "react";
import { Button } from "../../../web/shared/components/Button";
import type { FollowupTask } from "../invoice-followup-data";
import {
  notificationScenes,
  supplierNotificationChannel,
  type NotificationScene,
  type SupplierContact,
  type ManualNotificationRecord,
} from "../supplier-notification-data";
import "./supplier-notification.css";

type Props = {
  task: FollowupTask;
  scene: NotificationScene;
  onScene: (scene: NotificationScene) => void;
  contact: SupplierContact;
  onContact: (contact: SupplierContact) => void;
  manualRecord: ManualNotificationRecord | null;
  onManualRecord: (record: ManualNotificationRecord) => void;
  messageDraft: string | null;
  onMessageChange: (message: string | null) => void;
  preview: (value: { title: string; content: string }) => void;
};

export function SupplierNotification({
  task,
  scene,
  onScene,
  contact,
  onContact,
  manualRecord,
  onManualRecord,
  messageDraft,
  onMessageChange,
  preview,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(contact);
  const [feedback, setFeedback] = useState("");
  const [recording, setRecording] = useState(false);
  const [sentAt, setSentAt] = useState("2026-09-24T15:30");
  const [note, setNote] = useState("");
  const recordInput = useRef<HTMLInputElement>(null);
  const manualActions = useRef<HTMLDivElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const editButton = useRef<HTMLDivElement>(null);
  const state = notificationScenes[scene];
  const missing = scene === "missing";
  const locked = ["sending", "pending", "unknown", "sent", "recorded"].includes(scene);
  const record = manualRecord ?? {
    ...contact,
    sentAt: "2026-09-24T15:30",
    note: "已核对目标供应商群，手动发送通知及合同（固定示例）。",
  };
  const filename = `${task.purchase}${task.supplier}.pdf`;
  const defaultMessage = `【开票通知 · 演示】${task.purchase}\n${task.supplier}，您好：\n本次采购已通过财务审核，请核对合同后开具发票。\n采购公司：示例采购公司\n关联报关单：${task.declaration}\n子采购订单：${task.purchase}\n约定开票日期：${task.due}\n请在发票备注中注明子采购订单号。如已开票，请提供对应发票。\n合同文件：${filename}\n【以上均为虚构示例，请勿用于真实业务】`;
  const message =
    scene === "recorded" && manualRecord ? manualRecord.message : (messageDraft ?? defaultMessage);
  const emptyMessage = !message.trim();
  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setFeedback("示例通知文字已复制；合同文件未复制，也未发送任何消息。");
    } catch {
      setFeedback("浏览器未允许复制，请在完整预览中手动选择文字复制。");
    }
  };
  const edit = () => {
    setDraft(contact);
    setEditing(true);
    requestAnimationFrame(() => nameInput.current?.focus());
  };
  const close = () => {
    setEditing(false);
    requestAnimationFrame(() => editButton.current?.querySelector("button")?.focus());
  };
  const showNotice = () =>
    preview({
      title: "供应商开票通知预览（示例）",
      content: `渠道：${supplierNotificationChannel}\n接收群：${missing ? "尚未绑定" : contact.groupName}\n内部对接人：${missing ? "待补充" : contact.owner}\n\n${message}\n\n操作说明：核对目标群后，由员工在企微确认发送。手动发送时从共享盘取对应合同一并发送；此处不下载或上传文件。`,
    });
  return (
    <div className="sn-demo">
      <div className="sn-scenes">
        <div>
          <strong>通知状态示例</strong>
          <p>切换查看不同处理场景，所有群名称、对接人和记录均为虚构。</p>
        </div>
        <label>
          预览状态
          <select
            value={scene}
            onChange={(event) => {
              onScene(event.target.value as NotificationScene);
              setFeedback("");
              setEditing(false);
              setRecording(false);
            }}
          >
            {Object.entries(notificationScenes).map(([key, item]) => (
              <option key={key} value={key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="sn-help">
        发送流程：准备通知 → 创建员工发送任务 → 员工在企微确认 →
        查询实际发送结果。创建任务成功不等于已发送给供应商。
      </p>
      <div className="sn-result" data-tone={state.tone} role="status">
        <div>
          <strong>
            {state.label}
            <span>演示状态</span>
          </strong>
          <p>{state.description}</p>
          <p>{state.next}</p>
        </div>
        {missing ? (
          <Button variant="primary" onClick={edit}>
            绑定企微外部群
          </Button>
        ) : scene === "queued" ? (
          <Button
            variant="primary"
            disabled={emptyMessage}
            onClick={() => {
              onScene("pending");
              setRecording(false);
              setFeedback("已切换到待员工发送场景；未调用企微接口或创建真实任务。");
            }}
          >
            演示创建通知
          </Button>
        ) : scene === "pending" ? (
          <Button
            variant="primary"
            onClick={() => {
              onScene("sent");
              setFeedback("仅演示员工确认并查询到发送成功的结果，未实际发送。");
            }}
          >
            演示员工确认发送
          </Button>
        ) : scene === "failed" ? (
          <Button
            variant="primary"
            onClick={() => {
              onScene("queued");
              setFeedback("已切换到待创建通知示例；未创建真实发送请求。");
            }}
          >
            演示重试
          </Button>
        ) : scene === "unknown" ? (
          <Button
            onClick={() =>
              preview({
                title: "发送结果核实（示例）",
                content: `示例通知：NOTICE-DEMO-001\n子采购单：${task.purchase}\n渠道：${supplierNotificationChannel}\n接收群：${contact.groupName}\n\n发送后未收到回执，不能推断为失败。正式接入后需要查询渠道发送记录，确认未发送再允许重试。\n\n此处仅演示核实信息，没有调用渠道接口。`,
              })
            }
          >
            查看核实信息
          </Button>
        ) : (
          <Button onClick={showNotice}>预览通知</Button>
        )}
      </div>
      {feedback && (
        <p className="sn-feedback" role="status">
          {feedback}
        </p>
      )}
      {scene === "queued" && (
        <section className="sn-manual" aria-label="人工发送登记">
          <div className="sn-heading">
            <h3>接口接入前：人工发送后登记</h3>
            <div ref={manualActions}>
              <Button
                disabled={emptyMessage}
                onClick={() => {
                  setRecording(true);
                  requestAnimationFrame(() => recordInput.current?.focus());
                }}
              >
                人工登记已发送（示例）
              </Button>
            </div>
          </div>
          <p className="sn-help">
            采购人员核对供应商群，发送通知和共享盘中的合同后，再登记发送情况。本示例不会操作企微。
          </p>
          {recording && (
            <form
              className="sn-form"
              onSubmit={(event) => {
                event.preventDefault();
                onManualRecord({ ...contact, sentAt, note, message });
                onScene("recorded");
                setRecording(false);
                setFeedback("已保存当前页面的人工登记示例，未获得企微发送回执；刷新后恢复。");
              }}
            >
              <p>
                登记发送人：{contact.owner}
                <br />
                目标外部群：{contact.groupName}
              </p>
              <label>
                发送时间（示例）
                <input
                  ref={recordInput}
                  type="datetime-local"
                  required
                  value={sentAt}
                  onChange={(event) => setSentAt(event.target.value)}
                />
              </label>
              <label>
                登记说明
                <input
                  required
                  maxLength={200}
                  value={note}
                  placeholder="例如：已核对目标群并发送通知与合同（示例）"
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>
              <div className="sn-form-actions">
                <Button type="submit" variant="primary" disabled={emptyMessage}>
                  保存人工登记示例
                </Button>
                <Button
                  onClick={() => {
                    setRecording(false);
                    requestAnimationFrame(() => manualActions.current?.querySelector("button")?.focus());
                  }}
                >
                  取消
                </Button>
              </div>
            </form>
          )}
        </section>
      )}
      <div className="sn-columns">
        <section className="sn-contact" aria-labelledby="sn-contact-title">
          <div className="sn-heading">
            <h3 id="sn-contact-title">企微外部群</h3>
            <div ref={editButton}>
              <Button disabled={locked} onClick={edit}>
                配置外部群
              </Button>
            </div>
          </div>
          <p className="sn-help">按供应商绑定外部群，后续任务复用；发送记录保留当时的群信息。</p>
          {editing ? (
            <form
              className="sn-form"
              onSubmit={(event) => {
                event.preventDefault();
                onContact(draft);
                if (scene === "missing" || scene === "failed") onScene("queued");
                setFeedback("外部群绑定已应用于当前示例，仅在此页面有效；刷新恢复，不会发送通知。");
                close();
              }}
            >
              <label>
                内部对接人
                <input
                  ref={nameInput}
                  required
                  maxLength={60}
                  value={draft.owner}
                  onChange={(event) => setDraft({ ...draft, owner: event.target.value })}
                />
              </label>
              <p className="sn-help">通知渠道：企微外部群</p>
              <label>
                外部群名称
                <input
                  required
                  maxLength={160}
                  placeholder="例如：供应商开票对接群（示例）"
                  value={draft.groupName}
                  onChange={(event) => setDraft({ ...draft, groupName: event.target.value })}
                />
              </label>
              <p className="sn-help">
                此处仅填写示例群名称体验绑定。正式接入时选择对应的企微外部群，不能仅凭群名称发送。
              </p>
              <div className="sn-form-actions">
                <Button type="submit" variant="primary">
                  保存示例配置
                </Button>
                <Button onClick={close}>取消</Button>
              </div>
            </form>
          ) : (
            <dl className="sn-fields">
              <div>
                <dt>供应商</dt>
                <dd>{task.supplier}</dd>
              </div>
              <div>
                <dt>内部对接人</dt>
                <dd>{missing ? "待补充" : contact.owner}</dd>
              </div>
              <div>
                <dt>通知渠道</dt>
                <dd>{supplierNotificationChannel}</dd>
              </div>
              <div>
                <dt>外部群名称</dt>
                <dd>{missing ? "尚未绑定" : contact.groupName}</dd>
              </div>
              <div>
                <dt>发送规则</dt>
                <dd>系统准备通知，员工在企微核对并确认发送</dd>
              </div>
            </dl>
          )}
          {locked && (
            <p className="sn-help">
              {scene === "sent" || scene === "recorded"
                ? "已发送通知保留当时的外部群信息；后续修改绑定不影响历史记录。"
                : "员工发送任务处理中或结果待核实，暂不修改本次外部群绑定。"}
            </p>
          )}
        </section>
        <section className="sn-message" aria-labelledby="sn-message-title">
          <div className="sn-heading">
            <h3 id="sn-message-title">本次通知</h3>
            <Button onClick={showNotice}>预览完整内容</Button>
          </div>
          <dl className="sn-fields">
            <div>
              <dt>采购公司</dt>
              <dd>示例采购公司</dd>
            </div>
            <div>
              <dt>关联报关单</dt>
              <dd>{task.declaration}</dd>
            </div>
            <div>
              <dt>子采购订单</dt>
              <dd>{task.purchase}</dd>
            </div>
          </dl>
          <div className="sn-message-editor">
            <div className="sn-heading">
              <label htmlFor="sn-message-body">通知正文</label>
              <span className="sn-help">{message === defaultMessage ? "默认模板" : "已手动编辑"}</span>
            </div>
            <textarea
              id="sn-message-body"
              rows={12}
              value={message}
              readOnly={locked}
              required
              aria-invalid={emptyMessage}
              aria-describedby="sn-message-help"
              onChange={(event) => onMessageChange(event.target.value)}
            />
            <p id="sn-message-help" className="sn-help">
              {emptyMessage
                ? "请输入通知内容后再创建通知或登记发送。"
                : locked
                  ? "本次通知已提交或已有发送记录，内容只读，保留当时版本。"
                  : "已按本次采购生成默认通知，可直接编辑；修改仅用于当前任务示例，刷新后恢复。"}
            </p>
          </div>
          <div className="sn-form-actions">
            <Button onClick={copyMessage} disabled={emptyMessage}>
              复制示例通知文字
            </Button>
            <Button
              disabled={locked || message === defaultMessage}
              onClick={() => {
                onMessageChange(null);
                setFeedback("已恢复本次采购的默认通知模板。");
              }}
            >
              恢复默认模板
            </Button>
          </div>
          <div className="sn-attachment">
            <span aria-hidden="true">PDF</span>
            <div>
              <strong>{filename}</strong>
              <p>共享盘已保存（示例） · 手动发送时一并附送</p>
            </div>
          </div>
          <p className="sn-help">
            拟随群通知附送合同文件，供应商无需访问公司共享盘；实际发送与附件能力待接入验证。
          </p>
        </section>
      </div>
      <section className="sn-records" aria-labelledby="sn-records-title">
        <div className="sn-heading">
          <h3 id="sn-records-title">通知记录</h3>
          <span className="sn-help">以下时间、回执均为示例</span>
        </div>
        {scene === "missing" || scene === "queued" ? (
          <div className="sn-empty">
            <strong>暂无发送记录</strong>
            <p>
              {missing
                ? "绑定供应商企微外部群后，准备员工发送任务。"
                : "尚未创建员工发送任务，也没有人工发送登记。"}
            </p>
          </div>
        ) : (
          <div className="sn-log">
            <div className="sn-log-title">
              <strong>{scene === "recorded" ? "人工发送登记" : "首次开票通知"}</strong>
              <span className={`if-status if-status--${state.tone}`}>{state.label}</span>
            </div>
            <dl className="sn-fields">
              <div>
                <dt>{scene === "recorded" ? "登记发送时间" : "任务提交时间"}</dt>
                <dd>{scene === "recorded" ? record.sentAt.replace("T", " ") : "2026-09-24 15:30"}（示例）</dd>
              </div>
              <div>
                <dt>接收快照</dt>
                <dd>
                  {supplierNotificationChannel} · {scene === "recorded" ? record.owner : contact.owner} ·{" "}
                  {scene === "recorded" ? record.groupName : contact.groupName}
                </dd>
              </div>
              <div>
                <dt>结果来源</dt>
                <dd>
                  {scene === "recorded" ? "人工登记 · 未经企微接口核验" : "企微任务查询（模拟，接口未接入）"}
                </dd>
              </div>
              <div>
                <dt>{scene === "recorded" ? "登记说明" : "处理结果"}</dt>
                <dd>
                  {scene === "sent"
                    ? "已查询到目标群发送成功（示例）· 不代表供应商已读"
                    : scene === "recorded"
                      ? record.note
                      : scene === "pending"
                        ? `任务已创建，等待 ${contact.owner} 在企微确认；尚未发送`
                        : scene === "failed"
                          ? "外部群不可用，创建员工发送任务失败（示例）"
                          : scene === "unknown"
                            ? "回执超时，需核实原通知"
                            : "正在创建员工发送任务，尚未发送给供应商"}
                </dd>
              </div>
            </dl>
          </div>
        )}
      </section>
    </div>
  );
}
