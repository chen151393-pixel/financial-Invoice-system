import { useCallback, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { SupplierOwnerEditor } from "../components/SupplierOwnerEditor";
import { SupplierOwnerHistory } from "../components/SupplierOwnerHistory";
import { SupplierOwnerSearch } from "../components/SupplierOwnerSearch";
import { SupplierOwnerTable, ownerKey } from "../components/SupplierOwnerTable";
import { SupplierTabs } from "../components/SupplierTabs";
import { useSupplierOwners } from "../hooks/useSupplierOwners";
import type { OwnerItem, OwnerQuery } from "../types/supplier-owner";
import "./supplier-owners.css";

export function SupplierOwnersPage() {
  const { state, query, search, reload } = useSupplierOwners();
  const [selected, setSelected] = useState<string[]>([]);
  const [editor, setEditor] = useState<{ key: number; items: OwnerItem[] } | null>({ key: 0, items: [] });
  const [history, setHistory] = useState<OwnerItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const nextEditor = useRef(0);
  const trigger = useRef<HTMLElement | null>(null);
  const onBusy = useCallback((value: boolean) => setBusy(value), []);
  function open(items: OwnerItem[]) {
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setFeedback("");
    setEditor({ key: ++nextEditor.current, items });
  }
  function close() {
    setEditor(null);
    trigger.current?.focus();
  }
  function change(next: OwnerQuery) {
    setSelected([]);
    setEditor(null);
    search(next);
  }
  return (
    <div className="supplier-owners">
      <SupplierTabs value="owners" />
      {feedback && <Alert tone="success">{feedback}</Alert>}
      {state.kind === "loading" && <Skeleton label="正在读取供应商人员关联" />}
      {state.kind === "error" && (
        <ErrorState
          title="人员关联暂时无法加载"
          message={state.message}
          action={<Button onClick={reload}>重新加载</Button>}
        />
      )}
      {state.kind === "ready" && (
        <div className="supplier-owner-layout">
          <Card className="supplier-owner-list">
            <CardHeader
              title="供应商人员关联"
              description="同一供应商可按不同采购抬头分配负责人"
              actions={
                <>
                  <Button
                    disabled={busy || !selected.length}
                    onClick={() => open(state.data.items.filter((r) => selected.includes(ownerKey(r))))}
                  >
                    批量更换负责人{selected.length ? `（${selected.length}）` : ""}
                  </Button>
                  <Button variant="primary" disabled={busy} onClick={() => open([])}>
                    新增关联
                  </Button>
                </>
              }
            />
            <SupplierOwnerSearch
              key={JSON.stringify(query)}
              query={query}
              options={state.options}
              onSearch={change}
              disabled={busy}
            />
            {state.data.items.length ? (
              <SupplierOwnerTable
                items={state.data.items}
                selected={selected}
                disabled={busy}
                onSelect={setSelected}
                onEdit={(r) => open([r])}
                onHistory={setHistory}
              />
            ) : (
              <EmptyState
                title="没有符合条件的人员关联"
                description="可以调整查询条件或新增供应商与采购抬头的人员关系；来源尚未出现时请先同步子采购单。"
              />
            )}
            <CardFooter>
              <Pagination
                label="供应商人员关联分页"
                total={state.data.total}
                page={state.data.page}
                pageCount={state.data.pages}
                pageSize={state.data.pageSize}
                pageSizes={[10, 20, 50]}
                onPageChange={(page) => {
                  if (!busy) change({ ...query, page });
                }}
                onPageSizeChange={(pageSize) => {
                  if (!busy) change({ ...query, page: 1, pageSize });
                }}
              />
            </CardFooter>
          </Card>
          {editor ? (
            <SupplierOwnerEditor
              key={editor.key}
              items={editor.items}
              options={state.options}
              onBusy={onBusy}
              onClose={close}
              onSaved={(message) => {
                setFeedback(message);
                setSelected([]);
                setEditor(null);
                reload();
              }}
            />
          ) : (
            <Card className="supplier-owner-editor">
              <CardContent>
                <EmptyState
                  title="维护人员关联"
                  description="点击新增关联，或选择列表中的关系进行维护和批量更换负责人。"
                />
              </CardContent>
            </Card>
          )}
          <div className="supplier-owner-note">
            <Alert>人员变更可追溯。KPI 可按业务事实发生时的任务负责人统计，历史缺失归属保留“待确认”。</Alert>
          </div>
        </div>
      )}
      {history && <SupplierOwnerHistory item={history} onClose={() => setHistory(null)} />}
    </div>
  );
}
