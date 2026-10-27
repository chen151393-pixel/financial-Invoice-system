import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { ComparisonResult, ReviewFilter } from "../types";

/**
 * 财务核对概况：张数全部来自后端列表计数（随查询条件变化），前端只展示。
 * 四张卡均可点击；本月审核通过卡进入全部已审核列表，其余按对应范围筛选。
 */
export function ReviewStats({
  counts,
  value,
  onSelect,
}: {
  counts: ComparisonResult["counts"];
  value: ReviewFilter;
  onSelect: (status: ReviewFilter) => void;
}) {
  return (
    <StatGrid label="核对概况">
      <StatCard
        glyph="审"
        tone={counts.pending > 0 ? "warning" : "neutral"}
        label="待审核报关单"
        value={`${counts.pending} 张`}
        note={counts.changed > 0 ? `其中 ${counts.changed} 张来源变化需重审` : "审核通过后生成开票任务"}
        selected={value === "pending"}
        onSelect={() => onSelect("pending")}
      />
      <StatCard
        glyph="幅"
        tone={counts.marginAlert > 0 ? "warning" : "neutral"}
        label="申报幅度异常"
        value={`${counts.marginAlert} 张`}
        note="采购价超出报关价容差，审核前请与采购核实"
        selected={value === "margin_alert"}
        onSelect={() => onSelect("margin_alert")}
      />
      <StatCard
        glyph="自"
        tone="primary"
        label="可自动审核通过"
        value={`${counts.autoApprovable} 张`}
        note="关联、金额、币种齐全且申报幅度正常，可批量审核"
        selected={value === "auto"}
        onSelect={() => onSelect("auto")}
      />
      <StatCard
        glyph="月"
        label="本月审核通过"
        value={`${counts.approvedThisMonth} 张`}
        note="按北京时间自然月统计，点击查看全部审核通过"
        selected={value === "approved"}
        onSelect={() => onSelect("approved")}
      />
    </StatGrid>
  );
}
