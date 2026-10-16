import { GroupImportRows } from "./GroupImportRows";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { confirmGroups, getGroupPreview } from "../api/external-group";
import type { Association, PreviewPage, PreviewRow } from "../types/external-group";
import { SupplierAssociation } from "./SupplierAssociation";

export function GroupImportPreview({
  importId,
  onDone,
  onClose,
}: {
  importId: string;
  onDone: (message: string) => void;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [load, setLoad] = useState(0);
  const [state, setState] = useState<{ data?: PreviewPage; error?: string; key?: string }>({});
  const [choices, setChoices] = useState<Record<number, Association>>({});
  const [editing, setEditing] = useState<PreviewRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const initialized = useRef(false);
  const key = `${importId}:${page}:${load}`;
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    let active = true;
    void getGroupPreview(importId, page).then(
      (data) => {
        if (active) {
          setState({ data, key });
          if (!initialized.current) {
            initialized.current = true;
            setChoices(Object.fromEntries(data.suggestions.map(({ rowNo, ...choice }) => [rowNo, choice])));
          }
        }
      },
      (reason) => {
        if (active) setState({ error: reason instanceof Error ? reason.message : "预览读取失败", key });
      },
    );
    return () => {
      active = false;
    };
  }, [importId, page, load, key]);
  const data = state.key === key ? state.data : undefined;
  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await confirmGroups(importId, choices);
      onDone(
        `${result.message}。导入 ${result.imported} 个群，保存 ${result.bound} 项绑定，跳过 ${result.skipped} 条错误行。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "确认失败，请保留当前预览核实结果");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="eg-preview" aria-label="导入匹配预览">
      <div className="sg-row sg-between">
        <h2 ref={heading} tabIndex={-1}>
          导入匹配预览
        </h2>
        <Button disabled={busy} onClick={onClose}>
          返回群目录
        </Button>
      </div>
      {state.key !== key && <p role="status">正在读取匹配预览…</p>}
      {state.key === key && state.error && (
        <div role="alert">
          <p>{state.error}</p>
          <Button onClick={() => setLoad((v) => v + 1)}>重试读取</Button>
        </div>
      )}
      {data && (
        <>
          <p>
            {data.filename} · 共 {data.total} 行，有效 {data.valid} 行，错误 {data.invalid} 行；有候选{" "}
            {data.matched} 行，无候选 {data.unmatched} 行。
          </p>
          <p className="it-help">
            唯一且无冲突的候选已预选，请核对后确认；其余可手动关联。未选择的有效群也会导入目录。刷新后恢复初始推荐，请重新核对；预览有效期
            24 小时。
          </p>
          {editing && (
            <SupplierAssociation
              key={editing.rowNo}
              groupName={editing.groupName}
              candidates={editing.candidates}
              initial={choices[editing.rowNo]}
              busy={busy}
              onClose={() => {
                setEditing(null);
                heading.current?.focus();
              }}
              onApply={(value) => {
                setChoices((current) => ({ ...current, [editing.rowNo]: value }));
                setEditing(null);
                heading.current?.focus();
              }}
            />
          )}
          <GroupImportRows
            data={data}
            choices={choices}
            busy={busy}
            editing={!!editing}
            onEdit={setEditing}
            onClear={(rowNo) =>
              setChoices((current) => {
                const next = { ...current };
                delete next[rowNo];
                return next;
              })
            }
          />
          <Pagination
            label="导入预览分页"
            disabled={busy || !!editing}
            total={data.total}
            page={data.page}
            pageCount={data.pages}
            pageSize={20}
            pageSizes={[20]}
            onPageChange={(value) => {
              if (!busy && !editing) setPage(value);
            }}
            onPageSizeChange={() => {}}
          />
          <div className="sg-editor">
            <h3>确认导入</h3>
            <p>
              将导入 {data.valid} 个有效群，保存 {Object.keys(choices).length} 项已选关联；跳过 {data.invalid}{" "}
              条错误行。
            </p>
            {Object.keys(choices).length > 0 && (
              <ul>
                {Object.entries(choices).map(([rowNo, choice]) => (
                  <li key={rowNo}>
                    第 {rowNo} 行 → {choice.supplier.supplierName}（{choice.supplier.account}）
                    {choice.replaceExisting ? "，已确认替换原默认群" : ""}
                  </li>
                ))}
              </ul>
            )}
            <p className="it-help">
              {data.confirm.reason}。导入信息来自
              Excel，未经企微实时核验；不会发送消息。更新群目录不自动改写未勾选的供应商绑定。
            </p>
            {data.status === "confirmed" && <p role="status">该预览已确认，请返回群目录继续维护。</p>}
            {error && (
              <p role="alert" className="eg-error">
                {error}
              </p>
            )}
            <Button
              variant="primary"
              disabled={busy || !!editing || !data.confirm.allowed}
              onClick={() => void confirm()}
            >
              {busy ? "正在确认保存…" : "确认导入并保存所选绑定"}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
