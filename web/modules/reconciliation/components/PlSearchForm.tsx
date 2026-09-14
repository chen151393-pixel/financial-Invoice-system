import { useId, useState } from "react";
import { Button } from "../../../shared/components/Button";
import "./pl-search-form.css";

export interface PlSearchCriteria {
  pl: string;
  company: string;
}

interface PlSearchFormProps {
  onSearch: (criteria: PlSearchCriteria) => void;
  onReset: () => void;
  busy?: boolean;
  submitLabel: string;
}

/** 仅收集查询条件；数据源、匹配方式和查询结果由调用方提供。 */
export function PlSearchForm({ onSearch, onReset, busy = false, submitLabel }: PlSearchFormProps) {
  const id = useId();
  const [pl, setPl] = useState("");
  const [company, setCompany] = useState("");
  return (
    <form
      className="pl-search-form"
      role="search"
      aria-label="查询 PL 采购报关明细"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch({ pl, company });
      }}
      onReset={() => {
        setPl("");
        setCompany("");
        onReset();
      }}
    >
      <div className="pl-search-form__field">
        <label htmlFor={`${id}-pl`}>
          PL 单号<span>必填</span>
        </label>
        <input
          id={`${id}-pl`}
          name="pl"
          value={pl}
          onChange={(event) => setPl(event.target.value)}
          placeholder="例如 PL2510280002"
          aria-describedby={`${id}-pl-help`}
          required
          disabled={busy}
          autoComplete="off"
        />
        <p id={`${id}-pl-help`}>按完整 PL 单号查询对应的子采购订单和报关明细。</p>
      </div>
      <div className="pl-search-form__field">
        <label htmlFor={`${id}-company`}>
          申报公司<span>选填</span>
        </label>
        <input
          id={`${id}-company`}
          name="company"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          placeholder="公司名称、关键词或内部 ID"
          aria-describedby={`${id}-company-help`}
          disabled={busy}
          autoComplete="off"
        />
        <p id={`${id}-company-help`}>可填写公司抬头关键词；留空查看该 PL 下全部公司。</p>
      </div>
      <div className="pl-search-form__actions">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "查询中…" : submitLabel}
        </Button>
        <Button type="reset" disabled={busy}>
          重置
        </Button>
      </div>
    </form>
  );
}
