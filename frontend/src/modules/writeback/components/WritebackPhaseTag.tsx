import type { WritebackPhase } from "../types";

/** 状态文字来自后端；颜色只区分语义，文字始终显示，不单靠颜色表达。 */
export function WritebackPhaseTag({ phase, label }: { phase: WritebackPhase; label: string }) {
  return <span className={`wb-tag wb-tag--${phase}`}>{label}</span>;
}
