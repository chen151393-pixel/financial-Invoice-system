import { money } from "../../../shared/format/money";
import type { RecoverySummary } from "../types/recovery";

// 只组织后端给出的数字与文本，不重新计算口径。
export const yuan = (value: string | null | undefined) => (value ? `¥${money(value)}` : "—");
export const percent = (value: number | null | undefined) => (value == null ? "—" : `${value.toFixed(1)}%`);
export const unknownNote = (summary: RecoverySummary) =>
  summary.unknown ? ` · ${summary.unknown} 个金额待确认` : "";
export const shortDate = (value: string) => value.slice(5);
export function daysText(days: number | null) {
  if (days == null) return "";
  if (days < 0) return `已逾期 ${-days} 天`;
  return days === 0 ? "今天到期" : `剩 ${days} 天`;
}
// 万元展示只用于图表中心等空间受限处，明细仍显示完整金额
export function wan(value: string) {
  const number = Number(value);
  return number >= 10000 ? `¥${(number / 10000).toFixed(1)}万` : yuan(value);
}
