import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import "./finance-search-form.css";

export interface SearchCriteria {
  keyword: string;
  account: string;
  supplierId: string;
}

const EMPTY: SearchCriteria = { keyword: "", account: "", supplierId: "" };

export function FinanceSearchForm({
  busy,
  accounts,
  suppliers,
  onSearch,
  onRefresh,
  initial = EMPTY,
}: {
  busy: boolean;
  accounts: string[];
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
    <form
      className="fr-search"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(criteria);
      }}
    >
      <label htmlFor="finance-keyword">查找报关与采购单据</label>
      <div className="fr-search__row">
        <input
          id="finance-keyword"
          type="search"
          value={criteria.keyword}
          maxLength={120}
          placeholder="CD 编号 / 真实报关单号 / PL / 子采购单号 / 品名"
          onChange={(event) => change("keyword", event.target.value)}
        />
        <select
          aria-label="来源账套"
          value={criteria.account}
          onChange={(event) => change("account", event.target.value)}
        >
          <option value="">全部账套</option>
          {accounts.map((value) => (
            <option key={value} value={value}>
              NS {value}
            </option>
          ))}
        </select>
        <select
          className="fr-search__supplier"
          aria-label="供应商"
          value={criteria.supplierId}
          onChange={(event) => change("supplierId", event.target.value)}
        >
          <option value="">全部供应商</option>
          {suppliers.map((supplier) => (
            <option key={supplier.id} value={supplier.id}>
              {supplier.name}
            </option>
          ))}
        </select>
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
        <Button className="fr-search__refresh" disabled={busy} onClick={onRefresh}>
          刷新列表
        </Button>
      </div>
    </form>
  );
}
