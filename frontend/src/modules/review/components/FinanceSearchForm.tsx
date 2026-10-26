import { useState } from "react";
import { Button, Field, FilterBar } from "../../../shared/components/ui";

export interface SearchCriteria {
  keyword: string;
  supplierId: string;
}

const EMPTY: SearchCriteria = { keyword: "", supplierId: "" };

export function FinanceSearchForm({
  busy,
  suppliers,
  onSearch,
  onRefresh,
  initial = EMPTY,
}: {
  busy: boolean;
  // 供应商选项由后端按有效报关单关联的子采购单返回
  suppliers: { id: string; name: string }[];
  onSearch: (criteria: SearchCriteria) => void;
  onRefresh: () => void;
  initial?: SearchCriteria;
}) {
  const [criteria, setCriteria] = useState(initial);
  const change = (field: keyof SearchCriteria, value: string) =>
    setCriteria((current) => ({ ...current, [field]: value }));
  return (
    <FilterBar
      onSubmit={() => onSearch(criteria)}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            查询
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              setCriteria(EMPTY);
              onSearch(EMPTY);
            }}
          >
            清空
          </Button>
          <Button disabled={busy} onClick={onRefresh}>
            刷新列表
          </Button>
        </>
      }
    >
      <Field label="查找报关与采购单据" grow>
        <input
          id="finance-keyword"
          type="search"
          value={criteria.keyword}
          maxLength={120}
          placeholder="CD 编号 / 真实报关单号 / PL / 子采购单号 / 品名"
          onChange={(event) => change("keyword", event.target.value)}
        />
      </Field>
      <Field label="供应商">
        <select value={criteria.supplierId} onChange={(event) => change("supplierId", event.target.value)}>
          <option value="">全部供应商</option>
          {suppliers.map((supplier) => (
            <option key={supplier.id} value={supplier.id}>
              {supplier.name}
            </option>
          ))}
        </select>
      </Field>
    </FilterBar>
  );
}
