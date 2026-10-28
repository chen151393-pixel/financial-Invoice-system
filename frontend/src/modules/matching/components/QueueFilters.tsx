import { useState } from "react";
import { Button, Field, FilterBar, SearchInput } from "../../../shared/components/ui";
import type { QueueQuery } from "../types/matching";

type Filters = Pick<QueueQuery, "anomaly" | "invoiceNo" | "supplierName" | "invoiceFrom" | "invoiceTo">;
const EMPTY: Filters = { anomaly: "all", invoiceNo: "", supplierName: "", invoiceFrom: "", invoiceTo: "" };

/** 比对队列筛选：异常 / 正常、子采购单供应商、开票日期（起止须同时填写，由后端校验）。 */
export function QueueFilters({
  value,
  busy,
  onApply,
}: {
  value: Filters;
  busy: boolean;
  onApply: (filters: Filters) => void;
}) {
  const [draft, setDraft] = useState<Filters>(value);
  const set = (patch: Partial<Filters>) => setDraft((current) => ({ ...current, ...patch }));
  return (
    <FilterBar
      embedded
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
      <Field label="发票号码" hideLabel grow>
        <SearchInput
          name="invoiceNo"
          value={draft.invoiceNo}
          placeholder="输入发票号码，多条用逗号分隔"
          onValueChange={(invoiceNo) => set({ invoiceNo })}
        />
      </Field>
      <Field label="供应商" hideLabel grow>
        <SearchInput
          name="supplierName"
          value={draft.supplierName}
          placeholder="输入供应商名称，多条用逗号分隔"
          onValueChange={(supplierName) => set({ supplierName })}
        />
      </Field>
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
