import { Button, Field, FilterBar } from "../../../shared/components/ui";
import type { TaskList, TaskQuery } from "../types";

const fields = [
  { key: "taskNo", label: "任务号", placeholder: "输入回写任务号", max: 100 },
  { key: "invoiceNo", label: "发票号码", placeholder: "输入发票号码", max: 100 },
  { key: "supplierName", label: "供应商", placeholder: "输入供应商名称", max: 255 },
  { key: "parentOrderNo", label: "母采购单号", placeholder: "输入母采购单号", max: 100 },
] as const;

export function WritebackSearch({
  query,
  states,
  busy,
  onSearch,
  onReset,
}: {
  query: TaskQuery;
  states?: TaskList["states"];
  busy: boolean;
  onSearch: (patch: Partial<TaskQuery>) => void;
  onReset: () => void;
}) {
  return (
    <>
      <FilterBar
        key={JSON.stringify([query, Boolean(states)])}
        embedded
        onSubmit={(form) => {
          const values = new FormData(form);
          const state = String(values.get("state") || "");
          onSearch({
            taskNo: String(values.get("taskNo") || "").trim(),
            invoiceNo: String(values.get("invoiceNo") || "").trim(),
            supplierName: String(values.get("supplierName") || "").trim(),
            parentOrderNo: String(values.get("parentOrderNo") || "").trim(),
            state,
            group: state ? "" : query.group,
            page: 1,
          });
        }}
        actions={
          <>
            <Button type="submit" variant="primary" disabled={busy}>
              查询
            </Button>
            <Button disabled={busy} onClick={onReset}>
              清空条件
            </Button>
          </>
        }
      >
        {fields.map((field) => (
          <Field key={field.key} label={field.label} grow>
            <input
              type="search"
              name={field.key}
              defaultValue={query[field.key]}
              placeholder={field.placeholder}
              maxLength={field.max}
              disabled={busy}
            />
          </Field>
        ))}
        <Field label="细分状态">
          <select name="state" defaultValue={query.state} disabled={busy}>
            <option value="">{query.group ? "当前分组全部状态" : "全部细分状态"}</option>
            {states?.map((option) => (
              <option key={option.state} value={option.state}>
                {option.label}（{option.count}）
              </option>
            ))}
          </select>
        </Field>
      </FilterBar>
      {query.keyword && (
        <div className="wb-legacy-search" role="status">
          旧版综合关键词：{query.keyword}
          <Button size="sm" disabled={busy} onClick={() => onSearch({ keyword: "", page: 1 })}>
            清除综合关键词
          </Button>
        </div>
      )}
    </>
  );
}
