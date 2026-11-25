import { useState } from "react";
import { Button, Field, FilterBar, SearchInput } from "../../../shared/components/ui";
import type { CustomsCounts, CustomsDifferenceKind, CustomsSearch } from "../customs-types";

export const EMPTY_CUSTOMS_SEARCH: CustomsSearch = {
  declarationNo: "",
  name: "",
  consignee: "",
  exportFrom: "",
  exportTo: "",
  difference: "",
};

export const DIFFERENCE_LABELS: Record<CustomsDifferenceKind, string> = {
  quantity_mismatch: "数量不一致",
  unit_mismatch: "单位不一致",
  total_mismatch: "总价不一致",
  line_missing: "品名缺行",
};
const DIFFERENCE_COUNTS: Record<CustomsDifferenceKind, (counts: CustomsCounts) => number> = {
  quantity_mismatch: (c) => c.quantityMismatch,
  unit_mismatch: (c) => c.unitMismatch,
  total_mismatch: (c) => c.totalMismatch,
  line_missing: (c) => c.lineMissing,
};

/**
 * 海关回执查询栏：条件提交给后端筛选，前端不过滤当前页。
 * 差异类型下拉的张数来自后端 counts（随查询条件变化，一张回执可属多类）。
 */
export function CustomsSearchForm({
  busy,
  counts,
  initial,
  onSearch,
}: {
  busy: boolean;
  counts: CustomsCounts | null;
  initial: CustomsSearch;
  onSearch: (criteria: CustomsSearch) => void;
}) {
  const [criteria, setCriteria] = useState(initial);
  const set = (field: keyof CustomsSearch, value: string) =>
    setCriteria((current) => ({ ...current, [field]: value }));
  return (
    <FilterBar
      embedded
      onSubmit={() => onSearch(criteria)}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            查询
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              setCriteria(EMPTY_CUSTOMS_SEARCH);
              onSearch(EMPTY_CUSTOMS_SEARCH);
            }}
          >
            清空
          </Button>
        </>
      }
    >
      <Field label="出口报关单号" grow>
        <SearchInput
          name="declarationNo"
          value={criteria.declarationNo}
          placeholder="可粘贴多行，逗号或分号分隔"
          onValueChange={(value) => set("declarationNo", value)}
        />
      </Field>
      <Field label="海关商品名称" grow>
        <input
          name="name"
          value={criteria.name}
          maxLength={120}
          placeholder="如 相纸"
          onChange={(event) => set("name", event.target.value)}
        />
      </Field>
      <Field label="境外收货人" grow>
        <input
          name="consignee"
          value={criteria.consignee}
          maxLength={120}
          placeholder="按回执中的名称搜索"
          onChange={(event) => set("consignee", event.target.value)}
        />
      </Field>
      <Field label="出口日期 从">
        <input
          type="date"
          name="exportFrom"
          value={criteria.exportFrom}
          onChange={(event) => set("exportFrom", event.target.value)}
        />
      </Field>
      <Field label="至">
        <input
          type="date"
          name="exportTo"
          aria-label="出口日期 至"
          value={criteria.exportTo}
          onChange={(event) => set("exportTo", event.target.value)}
        />
      </Field>
      <Field label="差异类型">
        <select
          name="difference"
          aria-label="差异类型"
          value={criteria.difference}
          onChange={(event) => set("difference", event.target.value)}
        >
          <option value="">全部类型</option>
          {(Object.keys(DIFFERENCE_LABELS) as CustomsDifferenceKind[]).map((kind) => (
            <option key={kind} value={kind}>
              {counts
                ? `${DIFFERENCE_LABELS[kind]}（${DIFFERENCE_COUNTS[kind](counts)} 张）`
                : DIFFERENCE_LABELS[kind]}
            </option>
          ))}
        </select>
      </Field>
    </FilterBar>
  );
}
