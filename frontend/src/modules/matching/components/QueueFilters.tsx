import { useState } from "react";
import { Button, Field, FilterBar } from "../../../shared/components/ui";
import type { QueueQuery } from "../types/matching";

type Filters = Pick<QueueQuery, "anomaly" | "supplierId" | "invoiceFrom" | "invoiceTo">;
const EMPTY: Filters = { anomaly: "all", supplierId: "", invoiceFrom: "", invoiceTo: "" };

/** 比对队列筛选：异常 / 正常、子采购单供应商、开票日期（起止须同时填写，由后端校验）。 */
export function QueueFilters({
  value,
  suppliers,
  busy,
  onApply,
}: {
  value: Filters;
  suppliers: { id: string; name: string }[];
  busy: boolean;
  onApply: (filters: Filters) => void;
}) {
  const [draft, setDraft] = useState<Filters>(value);
  const set = (patch: Partial<Filters>) => setDraft((current) => ({ ...current, ...patch }));
  return (
    <FilterBar
      onSubmit={() => onApply(draft)}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            查询
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              setDraft(EMPTY);
              onApply(EMPTY);
            }}
          >
            清除
          </Button>
        </>
      }
    >
      <Field label="建议类型">
        <select
          value={draft.anomaly}
          onChange={(event) => set({ anomaly: event.target.value as QueueQuery["anomaly"] })}
        >
          <option value="all">全部建议</option>
          <option value="abnormal">只看异常</option>
          <option value="normal">只看正常</option>
        </select>
      </Field>
      <Field label="供应商">
        <select value={draft.supplierId} onChange={(event) => set({ supplierId: event.target.value })}>
          <option value="">全部供应商</option>
          {suppliers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="开票日期 从">
        <input
          type="date"
          value={draft.invoiceFrom}
          onChange={(event) => set({ invoiceFrom: event.target.value })}
        />
      </Field>
      <Field label="至">
        <input
          type="date"
          value={draft.invoiceTo}
          onChange={(event) => set({ invoiceTo: event.target.value })}
        />
      </Field>
    </FilterBar>
  );
}
