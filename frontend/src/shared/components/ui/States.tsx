import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

/** 空状态：说明本次条件下没有数据及下一步可做什么；不用于加载中或失败。 */
export function EmptyState({
  title,
  description,
  action,
  icon = "search",
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="ui-state" role="status">
      <span className="ui-state__icon">
        <Icon name={icon} />
      </span>
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

/** 请求失败：显示后端中文原因与允许的恢复操作。 */
export function ErrorState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="ui-state ui-state--error" role="alert">
      <span className="ui-state__icon">
        <Icon name="alert" />
      </span>
      <strong>{title}</strong>
      <p>{message}</p>
      {action}
    </div>
  );
}

/** 加载骨架：只占位，不显示虚构数字；配套读屏文字。 */
export function Skeleton({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div className="ui-skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="ui-skeleton__row" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      ))}
      <span className="ui-sr-only">{label}</span>
    </div>
  );
}

/** 提示框：info 说明、warning 需注意、danger 阻塞或失败；重要提示放在关联内容旁，不做短暂消失的通知。 */
export function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className="ui-alert" data-tone={tone} role={tone === "danger" ? "alert" : "note"}>
      <Icon name={tone === "success" ? "check" : tone === "info" ? "bell" : "alert"} />
      <div>
        {title && <strong>{title}</strong>}
        <div>{children}</div>
      </div>
    </div>
  );
}
