import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { findSuppliers } from "../api/external-group";
import type { Association, Candidate, SupplierOptions } from "../types/external-group";

export function SupplierAssociation({
  groupName,
  candidates,
  initial,
  busy,
  onApply,
  onClose,
}: {
  groupName: string;
  candidates: Candidate[];
  initial?: Association;
  busy: boolean;
  onApply: (value: Association) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(initial?.supplier);
  const [replaceExisting, setReplace] = useState(initial?.replaceExisting ?? false);
  const [query, setQuery] = useState<{ keyword: string; account: string; page: number } | null>(null);
  const [state, setState] = useState<{ data?: SupplierOptions; error?: string; key?: string }>({});
  const [refresh, setRefresh] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const key = JSON.stringify(query);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    if (key === "null") return;
    let active = true;
    const value = JSON.parse(key) as NonNullable<typeof query>;
    void findSuppliers(value.keyword, value.account, value.page).then(
      (data) => {
        if (active) setState({ data, key });
      },
      (error) => {
        if (active) setState({ error: error instanceof Error ? error.message : "供应商读取失败", key });
      },
    );
    return () => {
      active = false;
    };
  }, [key, refresh]);
  const loading = query !== null && state.key !== key;
  const options: Candidate[] = query ? (state.key === key ? (state.data?.items ?? []) : []) : candidates;
  return (
    <section className="sg-editor eg-association" aria-label="选择关联供应商">
      <div className="sg-row sg-between">
        <h2 ref={heading} tabIndex={-1}>
          为“{groupName}”选择供应商
        </h2>
        <Button disabled={busy} onClick={onClose}>
          取消选择
        </Button>
      </div>
      <p className="it-help">
        名称候选仅作参考。可按子采购供应商名称搜索，并核对 NS 环境；选择后还需确认保存。
      </p>
      <form
        className="sg-row"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setState({});
          setRefresh((value) => value + 1);
          setQuery({
            keyword: String(f.get("keyword") || ""),
            account: String(f.get("account") || ""),
            page: 1,
          });
        }}
      >
        <label>
          供应商名称
          <input name="keyword" placeholder="输入供应商全称或关键词" disabled={busy} />
        </label>
        <label>
          NS 环境
          <input name="account" placeholder="全部环境" disabled={busy} />
        </label>
        <Button type="submit" disabled={busy || loading}>
          查询供应商
        </Button>
      </form>
      {loading && <p role="status">正在查询供应商…</p>}
      {state.key === key && state.error && <p role="alert">{state.error}</p>}
      {!loading && options.length === 0 && (
        <p className="it-help">暂无候选供应商，请搜索；未同步的供应商需先同步子采购订单。</p>
      )}
      <ul className="sg-options">
        {options.map((item) => (
          <li key={item.supplierId}>
            <span>
              <strong>{item.supplierName}</strong>
              <small>
                NS 环境：{item.account} · 供应商 ID：{item.supplierId}
              </small>
              {item.reason && <small>{item.reason}</small>}
              <small>
                {item.binding
                  ? `现有群：${item.binding.groupName}（${item.binding.enabled ? "启用" : "停用"}）`
                  : "尚未绑定默认群"}
              </small>
            </span>
            <Button
              disabled={busy}
              aria-pressed={selected?.supplierId === item.supplierId}
              onClick={() => {
                setSelected(item);
                setReplace(false);
              }}
            >
              选择供应商
            </Button>
          </li>
        ))}
      </ul>
      {query && state.key === key && state.data && (
        <Pagination
          label="供应商搜索分页"
          disabled={busy}
          total={state.data.total}
          page={state.data.page}
          pageCount={state.data.pages}
          pageSize={20}
          pageSizes={[20]}
          onPageChange={(page) => setQuery({ ...query, page })}
          onPageSizeChange={() => {}}
        />
      )}
      {selected && (
        <div className="sg-selection">
          <p>
            已选：<strong>{selected.supplierName}</strong> · {selected.account}
          </p>
          {selected.binding && (
            <>
              <p>
                原绑定：{selected.binding.groupName} · 群主 {selected.binding.employee} ·{" "}
                {selected.binding.chatId}
              </p>
              <label className="eg-check">
                <input
                  type="checkbox"
                  checked={replaceExisting}
                  disabled={busy}
                  onChange={(e) => setReplace(e.target.checked)}
                />
                我确认用当前群替换该供应商原有默认群
              </label>
            </>
          )}
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => onApply({ supplier: selected, replaceExisting })}
          >
            使用此关联
          </Button>
        </div>
      )}
    </section>
  );
}
