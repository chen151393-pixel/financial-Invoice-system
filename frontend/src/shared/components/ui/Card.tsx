import type { HTMLAttributes, ReactNode } from "react";

type Div = HTMLAttributes<HTMLDivElement>;
const cls = (base: string, extra?: string) => (extra ? `${base} ${extra}` : base);

/** 内容面板：白底、细边框、12px 圆角。按 CardHeader → CardContent → CardFooter 组合，不在 CardContent 里堆标题。 */
export function Card({ className, ...props }: Div) {
  return <div {...props} className={cls("ui-card", className)} />;
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cls("ui-card__header", className)}>
      <div className="ui-card__heading">
        <h3 className="ui-card__title">{title}</h3>
        {description && <p className="ui-card__description">{description}</p>}
      </div>
      {actions && <div className="ui-card__actions">{actions}</div>}
    </div>
  );
}

export function CardContent({ className, flush, ...props }: Div & { flush?: boolean }) {
  return (
    <div
      {...props}
      className={cls(flush ? "ui-card__content ui-card__content--flush" : "ui-card__content", className)}
    />
  );
}

export function CardFooter({ className, ...props }: Div) {
  return <div {...props} className={cls("ui-card__footer", className)} />;
}

/** 页面分区标题：左侧主色竖条 + 标题，可带数量与右侧操作（对应参考图的 Key Metrics 等分区）。 */
export function SectionTitle({
  title,
  count,
  actions,
  id,
}: {
  title: ReactNode;
  count?: ReactNode;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <div className="ui-section-title">
      <h2 id={id}>{title}</h2>
      {count !== undefined && <span className="ui-section-title__count">{count}</span>}
      {actions && <div className="ui-section-title__actions">{actions}</div>}
    </div>
  );
}
