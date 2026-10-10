import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import "./finance-search-form.css";

export function FinanceSearchForm({
  busy,
  accounts,
  onSearch,
  onRefresh,
}: {
  busy: boolean;
  accounts: string[];
  onSearch: (keyword: string, account: string) => void;
  onRefresh: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [account, setAccount] = useState("");
  return (
    <form
      className="fr-search"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(keyword, account);
      }}
    >
      <label htmlFor="finance-keyword">查找报关与采购单据</label>
      <div className="fr-search__row">
        <input
          id="finance-keyword"
          type="search"
          value={keyword}
          maxLength={120}
          placeholder="CD 编号 / 真实报关单号 / PL / 子采购单号 / 品名"
          onChange={(event) => setKeyword(event.target.value)}
        />
        <select aria-label="来源账套" value={account} onChange={(event) => setAccount(event.target.value)}>
          <option value="">全部账套</option>
          {accounts.map((value) => (
            <option key={value} value={value}>
              NS {value}
            </option>
          ))}
        </select>
        <Button type="submit" variant="primary" disabled={busy}>
          查询
        </Button>
        <Button
          disabled={busy}
          onClick={() => {
            setKeyword("");
            setAccount("");
            onSearch("", "");
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
