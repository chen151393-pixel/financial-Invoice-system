import { useState } from "react";
import { Button, Field, FilterBar } from "../../../shared/components/ui";
import type { WritebackQuery } from "../types";

type Filters = Pick<WritebackQuery, "vendor" | "invoiceNo" | "dateFrom" | "dateTo">;
const empty: Filters = { vendor: "", invoiceNo: "", dateFrom: "", dateTo: "" };

/** 只收集条件；点击查询后才提交给后端筛选，修改中的条件不影响已显示的结果。 */
export function WritebackFilters({
  value,
  disabled,
  onSubmit,
}: {
  value: Filters;
  disabled: boolean;
  onSubmit: (filters: Filters) => void;
}) {
  const [draft, setDraft] = useState(value);
  const field = (key: keyof Filters) => ({
    value: draft[key],
    onChange: (event: { target: { value: string } }) => setDraft({ ...draft, [key]: event.target.value }),
  });
  return (
    <FilterBar
      onSubmit={() => onSubmit(draft)}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={disabled}>
            查询
          </Button>
          <Button
            disabled={disabled}
            onClick={() => {
              setDraft(empty);
              onSubmit(empty);
            }}
          >
            重置
          </Button>
        </>
      }
    >
      <Field label="供应商" grow>
        <input type="search" placeholder="供应商名称关键字" {...field("vendor")} />
      </Field>
      <Field label="发票号码">
        <input type="search" placeholder="例如 26332000000412805519" {...field("invoiceNo")} />
      </Field>
      <Field label="开票日期 从">
        <input type="date" {...field("dateFrom")} />
      </Field>
      <Field label="至">
        <input type="date" {...field("dateTo")} />
      </Field>
    </FilterBar>
  );
}
