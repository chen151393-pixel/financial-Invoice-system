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
import type { BatchList, BatchQuery, BatchSummary, Route, StatusFilter } from "../types";
import "../components/settlement.css";

type State = { kind: "loading" } | { kind: "ready"; result: BatchList } | { kind: "error"; message: string };

// 直接收汇没有“资料已出”环节，状态筛选按路径给出
const STATUSES: Record<Route, readonly { value: StatusFilter; label: string }[]> = {
  hk_transit: [
    { value: "open", label: "未完结" },
    { value: "collected", label: "香港已收" },
    { value: "documents_ready", label: "资料已出" },
    { value: "settled", label: "已结汇" },
    { value: "cancelled", label: "已作废" },
    { value: "all", label: "全部" },
  ],
  direct: [
    { value: "open", label: "未完结" },
    { value: "settled", label: "已结汇" },
    { value: "cancelled", label: "已作废" },
    { value: "all", label: "全部" },
  ],
};
const TITLES: Record<Route, { title: string; description: string; empty: string }> = {
  hk_transit: {
    title: "香港中转批次",
    description: "香港已收 → 资料已出 → 汇回对平后已结汇。",
    empty: "在“待结汇报关单”勾选香港中转的报关单并登记回款即可建批次。",
  },
  direct: {
    title: "直接收汇批次",
    description: "到账加手续费等于报关合计即可确认已结汇。",
    empty: "在“待结汇报关单”勾选直接收汇的报关单并登记回款即可建批次。",
  },
};
const INITIAL: Omit<BatchQuery, "route"> = {
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
    key: "status",
    header: "状态",
    render: (row) => (
      <Badge
        tone={row.status === "settled" ? "success" : row.status === "cancelled" ? "neutral" : "progress"}
      >
        {row.statusLabel}
      </Badge>
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

/** 某一回款路径的结汇批次列表：跟进资料、汇回与结汇确认。 */
export function SettlementBatchesPage({ route }: { route: Route }) {
  const [query, setQuery] = useState<BatchQuery>({ ...INITIAL, route });
  const text = TITLES[route];
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
      <Card>
        <CardHeader
          title={text.title}
          description={text.description}
          actions={
            <Segmented
              label="批次状态"
              value={query.status}
              options={STATUSES[route]}
              onChange={(status) => setQuery({ ...query, status, page: 1 })}
            />
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
                label={text.title}
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
              <EmptyState title="没有符合条件的结汇批次" description={text.empty} />
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
