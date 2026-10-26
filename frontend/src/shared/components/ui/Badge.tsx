import type { ReactNode } from "react";

/**
 * 状态徽标：语义色固定，必须带中文文字，不只靠颜色。
 * warning=待处理（橙）、info=等待外部（蓝）、progress=部分完成（紫）、success=已完成（绿）、danger=失败/阻塞、neutral=已替代/未开始。
 * 业务模块把自己的状态映射成 tone，不在页面另配颜色。
 */
export type Tone = "neutral" | "info" | "warning" | "progress" | "success" | "danger";

export function Badge({
  tone = "neutral",
  dot = true,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className="ui-badge" data-tone={tone} data-dot={dot || undefined}>
      {children}
    </span>
  );
}
