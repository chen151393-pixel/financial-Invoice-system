import { SettlementProgressPanel } from "../components/SettlementProgressPanel";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { OverviewInsights } from "../components/OverviewInsights";
import "../components/overview-insights.css";
import { OverviewCustomers } from "../components/OverviewCustomers";
import { OverviewMetrics } from "../components/OverviewMetrics";
import { OverviewRoutes } from "../components/OverviewRoutes";
import { useSettlementOverview } from "../hooks/useSettlementOverview";
import type { OverviewQuery } from "../types/overview";
import "../components/settlement.css";
import "../components/settlement-overview.css";

function OverviewFilters({
  query,
  currencies,
  busy,
  onQuery,
}: {
  query: OverviewQuery;
  currencies: string[];
  busy: boolean;
  onQuery: (query: OverviewQuery) => void;
}) {
  const [consignee, setConsignee] = useState(query.consignee);
  const [currency, setCurrency] = useState(query.currency);
  return (
    <FilterBar
      onSubmit={() => onQuery({ ...query, consignee: consignee.trim(), currency, page: 1 })}
      pending={
        consignee.trim() !== query.consignee || currency !== query.currency
          ? "条件已修改，查询后更新合计和明细"
          : undefined
      }
      actions={
        <>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "查询中…" : "查询"}
          </Button>
          <Button
            type="button"
            onClick={() => onQuery({ consignee: "", currency: "", page: 1, pageSize: 20 })}
          >
            清空
          </Button>
        </>
      }
    >
      <span className="settlement-overview-scope">统计范围：累计</span>
      <Field label="境外收货人" grow>
        <input
          value={consignee}
          onChange={(event) => setConsignee(event.target.value)}
          placeholder="按名称搜索"
        />
      </Field>
      <Field label="币种">
        <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
          <option value="">全部币种（分别统计）</option>
          {Array.from(new Set([...currencies, ...(query.currency ? [query.currency] : [])])).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </Field>
    </FilterBar>
  );
}

/** 累计收汇总览：同一筛选范围的应收、客户实收、未收差额；业务操作仍在原页面办理。 */
export function SettlementOverviewPage() {
  const [params, setParams] = useSearchParams();
  const query = useMemo<OverviewQuery>(
    () => ({
      consignee: params.get("consignee") || "",
      currency: params.get("currency") || "",
      page: Number(params.get("page") || 1),
      pageSize: Number(params.get("pageSize") || 20),
    }),
    [params],
  );
  const { state, reload, revision } = useSettlementOverview(query);
  function update(next: OverviewQuery) {
    const values = new URLSearchParams();
    if (next.consignee) values.set("consignee", next.consignee);
    if (next.currency) values.set("currency", next.currency);
    if (next.page !== 1) values.set("page", String(next.page));
    if (next.pageSize !== 20) values.set("pageSize", String(next.pageSize));
    if (values.toString() === params.toString()) reload();
    else setParams(values);
  }
  return (
    <div className="settlement-page settlement-overview-page">
      {state.kind === "ready" &&
        state.result.totals.map((total) => <OverviewMetrics key={total.currency} total={total} />)}
      <OverviewFilters
        key={params.toString()}
        query={query}
        currencies={state.kind === "ready" ? state.result.currencies : []}
        busy={state.kind === "loading"}
        onQuery={update}
      />
      <SettlementProgressPanel consignee={query.consignee} currency={query.currency} revision={revision} />
      {state.kind === "ready" && state.result.totals.length > 0 && (
        <OverviewRoutes totals={state.result.totals} consignee={query.consignee} />
      )}
      {state.kind === "ready" &&
        state.result.insights?.map((data) => (
          <OverviewInsights key={data.currency} data={data} asOf={state.result.asOf ?? ""} />
        ))}
      <Card>
        <CardHeader
          title="未收最多的客户"
          description="按币种分别统计，按未收差额从高到低排序；点击客户名称查看该客户报关单。手续费单列，负数表示超收。"
        />
        <CardContent flush>
          {state.kind === "loading" && <Skeleton rows={5} label="正在读取收汇总览" />}
          {state.kind === "error" && (
            <ErrorState
              title="收汇总览读取失败"
              message={state.message}
              action={<Button onClick={reload}>重试</Button>}
            />
          )}
          {state.kind === "ready" && (
            <>
              {state.result.skipped.length > 0 && (
                <Alert tone="warning" title={`${state.result.skipped.length} 张报关单未计入应收`}>
                  {state.result.skipped.map((row) => `${row.declarationNo}（${row.reason}）`).join("；")}
                </Alert>
              )}
              {state.result.items.length ? (
                <OverviewCustomers rows={state.result.items} />
              ) : (
                <EmptyState
                  title="没有符合条件的收汇数据"
                  description="调整查询条件，或先导入海关回执、银行收汇并登记香港回款。"
                />
              )}
            </>
          )}
        </CardContent>
        {state.kind === "ready" && state.result.total > 0 && (
          <CardFooter>
            <Pagination
              label="收汇总览分页"
              unit="组"
              total={state.result.total}
              page={state.result.page}
              pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
              pageSize={state.result.pageSize}
              pageSizes={[20, 50]}
              onPageChange={(page) => update({ ...query, page })}
              onPageSizeChange={(pageSize) => update({ ...query, pageSize, page: 1 })}
            />
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
