import type { ReactNode } from "react";

export function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ui-panel live-section ${className}`}>
      <div className="live-heading">
        <h2>{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
