import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryDocumentGroups } from "../api/document-group-api";
import type { DirectDocumentQuery } from "../types";
import type { DocumentGroupList } from "../types/document-group";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; result: DocumentGroupList };
export function DirectDocumentGroupsPanel({
  consignee,
  refresh,
  onSelect,
}: {
  consignee: string;
  refresh: number;
  onSelect: (id: number) => void;
}) {
  const initial: DirectDocumentQuery = {
    grouping: "multiple",
    keyword: "",
    consignee,
    status: "all",
    page: 1,
    pageSize: 20,
  };
  const [query, setQuery] = useState(initial);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    queryDocumentGroups(query, abort.signal)
      .then((result) => {
        if (!abort.signal.aborted) setState({ kind: "ready", result });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setState({ kind: "error", message: e instanceof Error ? e.message : "资料组读取失败" });
      });
    return () => abort.abort();
  }, [query, refresh, retry]);
  function update(next: DirectDocumentQuery) {
    setState({ kind: "loading" });
    setQuery(next);
  }
  return (
    <Card>
      <CardHeader
        title="多票资料组"
        description="同客户、同币种的报关单统一办理；不同申报抬头分别生成合同。"
      />
      <FilterBar
        embedded
        onSubmit={(form) => {
          const data = new FormData(form);
          update({ ...query, keyword: String(data.get("keyword") || ""), page: 1 });
        }}
        actions={
          <>
            <Button type="submit" variant="primary">
              查询
            </Button>
            <Button type="reset" onClick={() => update(initial)}>
              重置
            </Button>
          </>
        }
      >
        <Field label="资料组 / 客户 / 报关单 / 申报抬头" grow>
          <input name="keyword" placeholder="输入关键词" />
        </Field>
      </FilterBar>
      <CardContent flush>
        {state.kind === "loading" && <Skeleton rows={3} label="正在读取资料组" />}
        {state.kind === "error" && (
          <ErrorState
            title="资料组读取失败"
            message={state.message}
            action={
              <Button
                onClick={() => {
                  setState({ kind: "loading" });
                  setRetry((n) => n + 1);
                }}
              >
                重试
              </Button>
            }
          />
        )}
        {state.kind === "ready" &&
          (state.result.items.length ? (
            <DataTable
              label="直接收汇资料组"
              minWidth={880}
              rows={state.result.items}
              rowKey={(r) => String(r.id)}
              columns={[
                {
                  key: "number",
                  header: "资料组",
                  render: (r) => (
                    <Button variant="ghost" size="sm" onClick={() => onSelect(r.id)}>
                      {r.groupNo}
                    </Button>
                  ),
                },
                { key: "buyer", header: "境外收货人", render: (r) => r.consignee },
                {
                  key: "members",
                  header: "组内报关单 / NS 申报抬头",
                  render: (r) => (
                    <div className="settlement-cell">
                      {r.members.map((m) => (
                        <span key={m.declarationNo}>
                          {m.declarationNo} · {m.exportCompany || "待核对"}
                        </span>
                      ))}
                    </div>
                  ),
                },
                {
                  key: "amount",
                  header: "报关合计",
                  align: "right",
                  render: (r) => `${r.currency} ${money(r.amount)}`,
                },
                {
                  key: "state",
                  header: "资料进度",
                  render: (r) => (
                    <Badge tone={r.status === "complete" ? "success" : "warning"}>{r.statusLabel}</Badge>
                  ),
                },
                {
                  key: "action",
                  header: "操作",
                  render: (r) => (
                    <Button size="sm" onClick={() => onSelect(r.id)}>
                      办理资料
                    </Button>
                  ),
                },
              ]}
            />
          ) : (
            <EmptyState
              title="还没有多票资料组"
              description="从“报关资料”打开单票资料组，点击“与其他报关单合并办理”。"
            />
          ))}
      </CardContent>
      {state.kind === "ready" && state.result.total > 0 && (
        <CardFooter>
          <Pagination
            label="直接收汇资料组分页"
            total={state.result.total}
            unit="组"
            page={state.result.page}
            pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
            pageSize={query.pageSize}
            pageSizes={[20, 50]}
            onPageChange={(page) => update({ ...query, page })}
            onPageSizeChange={(pageSize) => update({ ...query, pageSize, page: 1 })}
          />
        </CardFooter>
      )}
    </Card>
  );
}
