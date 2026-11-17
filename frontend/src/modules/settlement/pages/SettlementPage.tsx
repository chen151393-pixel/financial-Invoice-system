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
  Pagination,
  Segmented,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryBatches } from "../api";
import { BatchDetailDialog } from "../components/BatchDetailDialog";
import { CandidatePanel } from "../components/CandidatePanel";
import type { BatchList, BatchQuery, BatchSummary, RouteFilter, StatusFilter } from "../types";
import "../components/settlement.css";

type State = { kind: "loading" } | { kind: "ready"; result: BatchList } | { kind: "error"; message: string };

const ROUTES: readonly { value: RouteFilter; label: string }[] = [
  { value: "all", label: "全部路径" },
  { value: "hk_transit", label: "香港中转" },
  { value: "direct", label: "直接收汇" },
];
const STATUSES: readonly { value: StatusFilter; label: string }[] = [
  { value: "open", label: "未完结" },
  { value: "collected", label: "已收款" },
  { value: "documents_ready", label: "资料已出" },
  { value: "settled", label: "已结汇" },
  { value: "cancelled", label: "已作废" },
  { value: "all", label: "全部" },
];
const INITIAL: BatchQuery = {
  route: "all",
  status: "open",
  consignee: "",
  batchNo: "",
  declarationNo: "",
  page: 1,
  pageSize: 20,
};

const COLUMNS: Column<BatchSummary>[] = [
  {
    key: "no",
    header: "批次号",
    render: (row) => (
      <div className="settlement-cell">
        <strong>{row.batchNo}</strong>
        <span>{row.declarationCount} 张报关单</span>
      </div>
    ),
  },
  {
    key: "route",
    header: "路径 / 状态",
    render: (row) => (
      <div className="settlement-badges">
        <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
        <Badge
          tone={row.status === "settled" ? "success" : row.status === "cancelled" ? "neutral" : "progress"}
        >
          {row.statusLabel}
        </Badge>
      </div>
    ),
  },
  { key: "consignee", header: "境外收货人", render: (row) => row.consignee },
  { key: "received", header: "到账日期", render: (row) => row.receivedOn },
  {
    key: "declared",
    header: "报关合计",
    align: "right",
    render: (row) => `${row.currency} ${money(row.declaredTotal)}`,
  },
  {
    key: "balance",
    header: "金额核对",
    render: (row) => (
      <div className="settlement-badges">
        {row.balances.map((balance) => (
          <Badge key={balance.stage} tone={balance.balanced ? "success" : "danger"}>
            {balance.label}
            {balance.balanced ? "对平" : `差 ${balance.difference}`}
          </Badge>
        ))}
      </div>
    ),
  },
];

/** 结汇对账：上方待结汇报关单建批次，下方批次列表跟进资料与汇回。 */
export function SettlementPage() {
  const [query, setQuery] = useState<BatchQuery>(INITIAL);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [open, setOpen] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        setState({ kind: "ready", result: await queryBatches(query, controller.signal) });
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  const reload = () => setRefresh((n) => n + 1);

  return (
    <div className="settlement-page">
      <CandidatePanel
        onCreated={(id) => {
          reload();
          setOpen(id);
        }}
      />
      <Card>
        <CardHeader
          title="结汇批次"
          description="香港中转：香港已收 → 资料已出 → 汇回对平后已结汇；直接收汇：到账对平后已结汇。差额只认手续费。"
          actions={
            <div className="settlement-badges">
              <Segmented
                label="回款路径"
                value={query.route}
                options={ROUTES}
                onChange={(route) => setQuery({ ...query, route, page: 1 })}
              />
              <Segmented
                label="批次状态"
                value={query.status}
                options={STATUSES}
                onChange={(status) => setQuery({ ...query, status, page: 1 })}
              />
            </div>
          }
        />
        <CardContent flush>
          {state.kind === "loading" && <Skeleton rows={4} label="正在读取结汇批次" />}
          {state.kind === "error" && (
            <ErrorState
              title="结汇批次读取失败"
              message={state.message}
              action={<Button onClick={reload}>重试</Button>}
            />
          )}
          {state.kind === "ready" &&
            (state.result.items.length ? (
              <DataTable
                label="结汇批次"
                columns={[
                  ...COLUMNS,
                  {
                    key: "open",
                    header: "操作",
                    render: (row) => (
                      <Button size="sm" variant="secondary" onClick={() => setOpen(row.id)}>
                        查看
                      </Button>
                    ),
                  },
                ]}
                rows={state.result.items}
                rowKey={(row) => String(row.id)}
                minWidth={960}
              />
            ) : (
              <EmptyState
                title="没有符合条件的结汇批次"
                description="在上方勾选报关单并登记回款即可建批次。"
              />
            ))}
        </CardContent>
        {state.kind === "ready" && state.result.total > 0 && (
          <CardFooter>
            <Pagination
              label="结汇批次分页"
              total={state.result.total}
              unit="批"
              page={query.page}
              pageCount={Math.max(1, Math.ceil(state.result.total / query.pageSize))}
              pageSize={query.pageSize}
              pageSizes={[20, 50]}
              onPageChange={(page) => setQuery({ ...query, page })}
              onPageSizeChange={(pageSize) => setQuery({ ...query, pageSize, page: 1 })}
            />
          </CardFooter>
        )}
      </Card>
      {open !== null && <BatchDetailDialog batchId={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}
