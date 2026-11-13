import { Button, Field, FilterBar } from "../../../shared/components/ui";
import type { OwnerOptions, OwnerQuery } from "../types/supplier-owner";
import { initialOwnerQuery } from "../hooks/useSupplierOwners";

export function SupplierOwnerSearch({
  query,
  options,
  onSearch,
  disabled,
}: {
  query: OwnerQuery;
  options: OwnerOptions;
  onSearch: (query: OwnerQuery) => void;
  disabled: boolean;
}) {
  return (
    <FilterBar
      embedded
      onSubmit={(form) => {
        const data = new FormData(form);
        onSearch({
          ...query,
          supplierName: String(data.get("supplierName") || ""),
          companyId: data.get("companyId") ? Number(data.get("companyId")) : null,
          memberId: data.get("memberId") ? Number(data.get("memberId")) : null,
          status: data.get("status") as OwnerQuery["status"],
          page: 1,
        });
      }}
      actions={
        <>
          <Button variant="primary" type="submit" disabled={disabled}>
            查询
          </Button>
          <Button disabled={disabled} onClick={() => onSearch({ ...initialOwnerQuery })}>
            清空
          </Button>
        </>
      }
    >
      <Field label="供应商" grow>
        <input
          name="supplierName"
          defaultValue={query.supplierName}
          placeholder="输入供应商名称，多条用逗号分隔"
          disabled={disabled}
        />
      </Field>
      <Field label="采购抬头">
        <select name="companyId" defaultValue={query.companyId ?? ""} disabled={disabled}>
          <option value="">全部抬头</option>
          {options.companies.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="负责人">
        <select name="memberId" defaultValue={query.memberId ?? ""} disabled={disabled}>
          <option value="">全部人员</option>
          {options.members.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="关联状态">
        <select name="status" defaultValue={query.status} disabled={disabled}>
          <option value="all">全部状态</option>
          <option value="assigned">已关联</option>
          <option value="unassigned">未关联</option>
          <option value="scheduled">有待生效变更</option>
        </select>
      </Field>
    </FilterBar>
  );
}
