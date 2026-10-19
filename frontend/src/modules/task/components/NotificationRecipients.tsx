import { Link } from "react-router";
import { paths } from "../../../app/paths";
import type { NotificationDraft, TaskDetail } from "../types/task";

export function NotificationRecipients({
  detail,
  draft,
  disabled,
  onChange,
}: {
  detail: TaskDetail;
  draft: Omit<NotificationDraft, "revision">;
  disabled: boolean;
  onChange: (draft: Omit<NotificationDraft, "revision">) => void;
}) {
  const notification = detail.notification;
  const field = (key: "groupName" | "employee", label: string, max: number) => (
    <label className="itn-field">
      {label}
      <input
        value={draft[key]}
        disabled={disabled}
        maxLength={max}
        placeholder="仅用于人工发送登记"
        onChange={(event) => onChange({ ...draft, [key]: event.target.value })}
      />
    </label>
  );
  return (
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
      {field("groupName", "人工发送群名称", 200)}
      {field("employee", "人工发送员工", 100)}
      <p className="it-help">已保存的通知保留原内容，默认群配置变化不会覆盖历史记录。</p>
      <p className="it-help">{notification.edit.reason}</p>
    </section>
  );
}
