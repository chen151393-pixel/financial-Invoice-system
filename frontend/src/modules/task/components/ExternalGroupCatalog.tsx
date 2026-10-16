import { ExternalGroupRows } from "./ExternalGroupRows";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { associateGroup, queryExternalGroups } from "../api/external-group";
import type { Association, CatalogItem, CatalogPage } from "../types/external-group";
import { SupplierAssociation } from "./SupplierAssociation";

export function ExternalGroupCatalog() {
  const [query, setQuery] = useState({ keyword: "", status: "all", page: 1 });
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<{ data?: CatalogPage; error?: string; key?: string }>({});
  const [editing, setEditing] = useState<CatalogItem | null>(null);
  const [choice, setChoice] = useState<Association | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const key = `${JSON.stringify(query)}:${refresh}`;
  useEffect(() => {
    let active = true;
    void queryExternalGroups(query.keyword, query.status, query.page).then(
      (data) => {
        if (active) setState({ data, key });
      },
      (reason) => {
        if (active) setState({ error: reason instanceof Error ? reason.message : "群目录读取失败", key });
      },
    );
    return () => {
      active = false;
    };
  }, [query, refresh, key]);
  const data = state.key === key ? state.data : undefined;
  function close() {
    setEditing(null);
    setChoice(null);
    setError("");
    heading.current?.focus();
  }
  async function save() {
    if (!editing || !choice || busy) return;
    setBusy(true);
    setError("");
    try {
      await associateGroup(editing, choice);
      close();
      setMessage("供应商关联已保存，后续新通知将使用该默认群。");
      setRefresh((v) => v + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联保存失败，请刷新核实");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="eg-catalog" aria-label="已导入外部群目录">
      <h2 ref={heading} tabIndex={-1}>
        已导入外部群
      </h2>
      <p className="it-help">
        目录来源为已确认的
        Excel。可随时手动关联子采购供应商；同一群可以关联多个供应商，每个供应商保留一个默认群。
      </p>
      <form
        className="sg-row"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setQuery({
            keyword: String(f.get("keyword") || ""),
            status: String(f.get("status") || "all"),
            page: 1,
          });
          setRefresh((v) => v + 1);
        }}
      >
        <label>
          群名 / 群主 / ID
          <input name="keyword" placeholder="搜索已导入群" disabled={busy} />
        </label>
        <label>
          关联状态
          <select name="status" disabled={busy}>
            <option value="all">全部群</option>
            <option value="unbound">未关联</option>
            <option value="bound">已关联</option>
          </select>
        </label>
        <Button type="submit" disabled={busy}>
          查询群目录
        </Button>
      </form>
      {message && <p role="status">{message}</p>}
      {editing && (
        <>
          {!choice && (
            <SupplierAssociation
              key={editing.chatId}
              groupName={editing.groupName}
              candidates={editing.suppliers}
              initial={choice ?? undefined}
              busy={busy}
              onClose={close}
              onApply={(value) => {
                setChoice(value);
                setError("");
              }}
            />
          )}
          {choice && (
            <div className="sg-editor">
              <h3>确认关联</h3>
              <p>
                {editing.groupName} → {choice.supplier.supplierName}（{choice.supplier.account}）
              </p>
              <p>
                群主：{editing.employee} · {editing.userid}
              </p>
              <p className="it-help">保存的是 Excel 导入信息，不触发企微发送。</p>
              {error && (
                <p role="alert" className="eg-error">
                  {error}
                </p>
              )}
              <Button disabled={busy} onClick={() => setChoice(null)}>
                重新选择供应商
              </Button>
              <Button disabled={busy} onClick={close}>
                取消关联
              </Button>
              <Button variant="primary" disabled={busy} onClick={() => void save()}>
                {busy ? "正在保存…" : "确认保存绑定"}
              </Button>
            </div>
          )}
        </>
      )}
      {state.key !== key && <p role="status">正在加载群目录…</p>}
      {state.key === key && state.error && (
        <div role="alert">
          <p>{state.error}</p>
          <Button onClick={() => setRefresh((v) => v + 1)}>重新加载</Button>
        </div>
      )}
      {data && (
        <>
          <p className="it-help">
            共 {data.total} 个群 · {data.manage.reason}
          </p>
          {data.items.length === 0 ? (
            <div className="it-empty">
              <h3>暂无符合条件的外部群</h3>
              <p>请导入并确认 Excel，或调整筛选条件。</p>
            </div>
          ) : (
            <ExternalGroupRows
              data={data}
              disabled={busy || !!editing || !data.manage.allowed}
              onEdit={(group) => {
                setEditing(group);
                setChoice(null);
                setMessage("");
                setError("");
              }}
            />
          )}
          <Pagination
            label="外部群目录分页"
            disabled={busy || !!editing}
            total={data.total}
            page={data.page}
            pageCount={data.pages}
            pageSize={20}
            pageSizes={[20]}
            onPageChange={(page) => {
              if (!busy && !editing) setQuery({ ...query, page });
            }}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
