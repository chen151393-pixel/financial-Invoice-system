import { useEffect, useState } from "react";
import { Link } from "react-router";
import { paths } from "../../../app/paths";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryCandidates, queryLedger } from "../api";
import type { Candidate, CandidateList, CandidateQuery, LedgerTotal, RouteFilter } from "../types";
import { ConsigneeSummary } from "./ConsigneeSummary";
import { CreateBatchDialog } from "./CreateBatchDialog";
import { ReceivableStats } from "./ReceivableStats";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: CandidateList }
  | { kind: "error"; message: string };

const EMPTY: CandidateQuery = {
  consignee: "",
  declarationNo: "",
  route: "all",
  exportFrom: null,
  exportTo: null,
  targetAmount: "",
};

/**
 * 报关应收汇：按境外收货人汇总应收汇并显示回款路径。
 * 香港中转的报关单勾选后登记回款建批次；直接收汇的报关单不建批次，进入直接收汇明细。
 * 路径判定、能否建批次均由后端给出（handling、blockedReason），提交时后端再次校验。
 */
export function CandidatePanel({ onCreated }: { onCreated: (batchId: number) => void }) {
  const [query, setQuery] = useState<CandidateQuery>(EMPTY);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [directTotals, setDirectTotals] = useState<LedgerTotal[] | null>();
  const [selected, setSelected] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryCandidates(query, controller.signal);
        setState({ kind: "ready", result });
        setSelected(result.suggestion ?? []);
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    void queryLedger(
      { consignee: "", company: "", status: "all", byRecipient: true, page: 1, pageSize: 1 },
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setDirectTotals(result.totals);
      })
      .catch(() => {
        if (!controller.signal.aborted) setDirectTotals(null);
      });
    return () => controller.abort();
  }, []);

  const toggle = (row: Candidate) =>
    setSelected((current) =>
      current.includes(row.declarationNo)
        ? current.filter((number) => number !== row.declarationNo)
        : [...current, row.declarationNo],
    );

  const columns: Column<Candidate>[] = [
    {
      key: "pick",
      header: "选择",
      width: "56px",
      render: (row) =>
        row.handling === "batch" ? (
          <input
            type="checkbox"
            aria-label={`选择报关单 ${row.declarationNo}`}
            checked={selected.includes(row.declarationNo)}
            disabled={Boolean(row.blockedReason)}
            onChange={() => toggle(row)}
          />
        ) : (
          "—"
        ),
    },
    {
      key: "number",
      header: "报关单号 / CD",
      width: "150px",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{row.declarationNo}</strong>
          <span>{row.recordNo || "—"}</span>
        </div>
      ),
    },
    {
      key: "orders",
      header: "销售订单",
      width: "120px",
      render: (row) => row.salesOrders.join("、") || "—",
    },
    { key: "consignee", header: "境外收货人", render: (row) => row.consignee || "—" },
    { key: "date", header: "出口日期", width: "110px", render: (row) => row.exportDate || "—" },
    {
      key: "route",
      header: "回款路径",
      width: "110px",
      render: (row) => (
        <span title={row.routeBasis}>
          <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
        </span>
      ),
    },
    {
      key: "amount",
      header: "报关金额",
      align: "right",
      width: "150px",
      render: (row) => (row.amount ? `${row.currency} ${money(row.amount)}` : "—"),
    },
    {
      key: "state",
      header: "状态",
      width: "270px",
      render: (row) =>
        row.blockedReason ? (
          <Badge tone="warning">{row.blockedReason}</Badge>
        ) : row.handling === "ledger" ? (
          <Link to={paths.settlementDirect}>已进直接收汇明细</Link>
        ) : (
          <Badge tone="success">可建批次</Badge>
        ),
    },
  ];

  const failure = state.kind === "error" && (
    <ErrorState
      title="报关应收汇读取失败"
      message={state.message}
      action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
    />
  );

  return (
    <>
      {state.kind === "ready" && (
        <ReceivableStats
          combinedTotals={state.result.combinedTotals}
          totals={state.result.totals}
          unsettled={state.result.unsettled}
          directTotals={directTotals}
        />
      )}
      <Card>
        <CardHeader
          title="按境外收货人汇总"
          description="应收汇金额为该收货人全部报关单的海关回执成交总价之和，按币种分开。"
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setQuery({
              consignee: String(data.get("consignee") || "").trim(),
              declarationNo: String(data.get("declarationNo") || "").trim(),
              route: String(data.get("route") || "all") as RouteFilter,
              exportFrom: String(data.get("exportFrom") || "") || null,
              exportTo: String(data.get("exportTo") || "") || null,
              targetAmount: String(data.get("targetAmount") || "").trim(),
            });
          }}
          actions={
            <>
              <Button type="submit" variant="primary">
                查询
              </Button>
              <Button type="reset" onClick={() => setQuery(EMPTY)}>
                清空
              </Button>
            </>
          }
        >
          <Field label="境外收货人" grow>
            <input name="consignee" placeholder="如 HONGKONG VISION" />
          </Field>
          <Field label="报关单号" grow>
            <input name="declarationNo" />
          </Field>
          <Field label="回款路径">
            <select name="route" defaultValue={EMPTY.route}>
              <option value="all">全部</option>
              <option value="hk_transit">香港中转</option>
              <option value="direct">直接收汇</option>
            </select>
          </Field>
          <Field label="出口日期 从">
            <input type="date" name="exportFrom" />
          </Field>
          <Field label="至">
            <input type="date" name="exportTo" aria-label="出口日期 至" />
          </Field>
          <Field label="香港到账金额（到账 + 手续费）">
            <input name="targetAmount" inputMode="decimal" placeholder="推荐组合用" />
          </Field>
        </FilterBar>
        <CardContent flush>
          {state.kind === "loading" && <Skeleton rows={3} label="正在汇总报关应收汇" />}
          {failure}
          {state.kind === "ready" &&
            (state.result.consignees.length ? (
              <ConsigneeSummary rows={state.result.consignees} />
            ) : (
              <EmptyState
                title="没有符合条件的报关单"
                description="海关回执导入并匹配到 NS 报关单后出现在这里。"
              />
            ))}
        </CardContent>
      </Card>
      {state.kind !== "error" && (
        <Card>
          <CardHeader
            title="报关单明细"
            description="香港中转的报关单勾选后登记回款建批次；直接收汇的报关单不建批次，自动进入直接收汇明细。"
            actions={
              <Button disabled={!selected.length} onClick={() => setCreating(true)}>
                登记回款并建批次（{selected.length}）
              </Button>
            }
          />
          <CardContent flush>
            {state.kind === "loading" && <Skeleton rows={4} label="正在读取报关单明细" />}
            {state.kind === "ready" && (
              <>
                {state.result.suggestionNote && (
                  <Alert tone={state.result.suggestion ? "success" : "info"}>
                    {state.result.suggestionNote}
                  </Alert>
                )}
                {state.result.truncated && (
                  <Alert tone="warning">
                    符合条件的报关单共 {state.result.total} 张，下方只列出出口日期最近的{" "}
                    {state.result.items.length} 张；上方汇总按全部计算。请缩小查询条件查看其余报关单。
                  </Alert>
                )}
                {state.result.items.length ? (
                  <DataTable
                    label="报关单明细"
                    columns={columns}
                    rows={state.result.items}
                    rowKey={(row) => row.declarationNo}
                    rowTone={(row) => (selected.includes(row.declarationNo) ? "accent" : undefined)}
                    minWidth={980}
                  />
                ) : (
                  <EmptyState
                    title="没有符合条件的报关单"
                    description="海关回执导入并匹配到 NS 报关单后出现在这里。"
                  />
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
      {creating && (
        <CreateBatchDialog
          declarationNos={selected}
          defaultAmount={query.targetAmount}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            setSelected([]);
            setRefresh((n) => n + 1);
            onCreated(id);
          }}
        />
      )}
    </>
  );
}
