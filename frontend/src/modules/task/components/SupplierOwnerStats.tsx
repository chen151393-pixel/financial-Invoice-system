import { StatCard, StatGrid } from "../../../shared/components/ui";
import type { OwnerCounts, OwnerQuery } from "../types/supplier-owner";

export function SupplierOwnerStats({
  counts,
  query,
  disabled,
  onSearch,
}: {
  counts: OwnerCounts;
  query: OwnerQuery;
  disabled: boolean;
  onSearch: (query: OwnerQuery) => void;
}) {
  function filter(change: Partial<Pick<OwnerQuery, "status" | "groupStatus">>) {
    onSearch({ ...query, ...change, page: 1 });
  }

  return (
    <StatGrid label="人员关联与开票群概况">
      <StatCard
        glyph="全"
        label="全部关系"
        value={`${counts.all} 条`}
        note="按供应商与采购抬头计数"
        selected={query.status === "all" && query.groupStatus === "all"}
        disabled={disabled}
        onSelect={() => filter({ status: "all", groupStatus: "all" })}
      />
      <StatCard
        glyph="未"
        label="未分配人员"
        value={`${counts.unassigned} 条`}
        note="尚未配置负责人"
        tone={counts.unassigned ? "warning" : "neutral"}
        selected={query.status === "unassigned"}
        disabled={disabled}
        onSelect={() => filter({ status: query.status === "unassigned" ? "all" : "unassigned" })}
      />
      <StatCard
        glyph="人"
        label="已分配人员"
        value={`${counts.assigned} 条`}
        note="负责人已生效"
        selected={query.status === "assigned"}
        disabled={disabled}
        onSelect={() => filter({ status: query.status === "assigned" ? "all" : "assigned" })}
      />
      <StatCard
        glyph="群"
        label="已绑定开票群"
        value={`${counts.bound} 条`}
        note="包含已停用的绑定"
        selected={query.groupStatus === "bound"}
        disabled={disabled}
        onSelect={() => filter({ groupStatus: query.groupStatus === "bound" ? "all" : "bound" })}
      />
      <StatCard
        glyph="群"
        label="未绑定开票群"
        value={`${counts.unbound} 条`}
        note="供应商尚未配置开票群"
        tone={counts.unbound ? "warning" : "neutral"}
        selected={query.groupStatus === "unbound"}
        disabled={disabled}
        onSelect={() => filter({ groupStatus: query.groupStatus === "unbound" ? "all" : "unbound" })}
      />
    </StatGrid>
  );
}
