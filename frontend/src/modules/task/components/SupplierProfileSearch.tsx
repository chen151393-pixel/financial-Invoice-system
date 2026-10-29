import { useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button, Field, FilterBar, SearchInput } from "../../../shared/components/ui";
import type { SupplierProfileQuery } from "../types/supplier-group";

const FIELDS = [
  ["supplierName", "供应商", "输入供应商名称，多条用逗号分隔"],
  ["groupName", "外部群", "输入外部群名称，多条用逗号分隔"],
  ["owner", "群主", "输入群主姓名或账号，多条用逗号分隔"],
] as const;

export function SupplierProfileSearch({
  query,
  busy,
  onSearch,
  onRefresh,
}: {
  query: SupplierProfileQuery;
  busy: boolean;
  onSearch: (patch: Partial<SupplierProfileQuery>) => void;
  onRefresh: () => void;
}) {
  const [draft, setDraft] = useState(query);
  return (
    <FilterBar
      embedded
      onSubmit={() => onSearch({ ...draft, keyword: "", page: 1 })}
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            查询
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              const cleared = {
                ...draft,
                keyword: "",
                supplierName: "",
                groupName: "",
                owner: "",
                status: "all" as const,
              };
              setDraft(cleared);
              onSearch({ ...cleared, page: 1 });
            }}
          >
            清空
          </Button>
          <Button disabled={busy} onClick={onRefresh}>
            刷新
          </Button>
          <Link className="ui-button ui-button--secondary" to={paths.externalGroups}>
            外部群导入与关联
          </Link>
        </>
      }
    >
      {FIELDS.map(([field, label, placeholder]) => (
        <Field key={field} label={label} hideLabel grow>
          <SearchInput
            name={field}
            value={draft[field] || ""}
            placeholder={placeholder}
            onValueChange={(value) => setDraft((current) => ({ ...current, [field]: value }))}
          />
        </Field>
      ))}
      <Field label="绑定状态" hideLabel>
        <select
          name="status"
          value={draft.status}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              status: event.target.value as SupplierProfileQuery["status"],
            }))
          }
        >
          <option value="all">全部供应商</option>
          <option value="bound">已绑定开票群</option>
          <option value="unbound">未绑定</option>
          <option value="notify_off">已关闭通知</option>
          <option value="enabled">已绑定 · 启用</option>
          <option value="disabled">已绑定 · 停用</option>
        </select>
      </Field>
    </FilterBar>
  );
}
