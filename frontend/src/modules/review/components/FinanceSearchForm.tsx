import { useState } from "react";
import { Button, Field, FilterBar, SearchInput } from "../../../shared/components/ui";

export interface SearchCriteria {
  supplierName: string;
  recordNo: string;
  purchaseOrderNo: string;
  createdFrom: string;
  createdTo: string;
}

const EMPTY: SearchCriteria = {
  supplierName: "",
  recordNo: "",
  purchaseOrderNo: "",
  createdFrom: "",
  createdTo: "",
};
const FIELDS = [
  ["supplierName", "供应商", "输入供应商名称，多条用逗号分隔"],
  ["recordNo", "CD 号", "输入 CD 号，多条用逗号分隔"],
  ["purchaseOrderNo", "子采购单号", "输入子采购单号，多条用逗号分隔"],
] as const;

export function FinanceSearchForm({
  busy,
  onSearch,
  initial = EMPTY,
}: {
  busy: boolean;
  onSearch: (criteria: SearchCriteria) => void;
  initial?: SearchCriteria;
}) {
  const [criteria, setCriteria] = useState(initial);
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
              setCriteria(EMPTY);
              onSearch(EMPTY);
            }}
          >
            清空
          </Button>
        </>
      }
    >
      {FIELDS.map(([field, label, placeholder]) => (
        <Field key={field} label={label} hideLabel grow>
          <SearchInput
            name={field}
            value={criteria[field]}
            placeholder={placeholder}
            onValueChange={(value) => setCriteria((current) => ({ ...current, [field]: value }))}
          />
        </Field>
      ))}
      <Field label="报关单创建日期 从">
        <input
          type="date"
          name="createdFrom"
          value={criteria.createdFrom}
          onChange={(event) => setCriteria((current) => ({ ...current, createdFrom: event.target.value }))}
        />
      </Field>
      <Field label="至">
        <input
          type="date"
          name="createdTo"
          aria-label="报关单创建日期 至"
          value={criteria.createdTo}
          onChange={(event) => setCriteria((current) => ({ ...current, createdTo: event.target.value }))}
        />
      </Field>
    </FilterBar>
  );
}
