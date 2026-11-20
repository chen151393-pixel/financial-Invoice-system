import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { settlementReceiptPath } from "../../../app/paths";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Skeleton,
  Tabs,
} from "../../../shared/components/ui";
import { queryReceivables } from "../api";
import type {
  ReceivableCustomer,
  ReceivableList,
  ReceivableQuery,
  ReceivableStageFilter,
  RouteFilter,
} from "../types";
import { ConsigneeSummary } from "./ConsigneeSummary";
import { ReceivableStats } from "./ReceivableStats";
import { ReceivableTable } from "./ReceivableTable";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: ReceivableList }
  | { kind: "error"; message: string };

const VIEWS = [
  { key: "customers", label: "按客户汇总" },
  { key: "declarations", label: "报关单明细" },
] as const;
const STAGES: readonly ReceivableStageFilter[] = [
  "all",
  "unregistered",
  "collected",
  "remit",
  "unpaid",
  "partial",
  "settled",
  "issue",
  "alert",
];
const FILTER_NAMES = ["consignee", "declarationNo", "currency", "route", "exportFrom", "exportTo"] as const;
const EMPTY: ReceivableQuery = {
  consignee: "",
  declarationNo: "",
  route: "all",
  stage: "all",
  exportFrom: null,
  exportTo: null,
};

// 地址只保存界面筛选状态；筛选、推算、阶段与金额汇总全部在后端完成。
function readQuery(params: URLSearchParams): ReceivableQuery {
  const route = params.get("route");
  const stage = params.get("stage") as ReceivableStageFilter | null;
  return {
    consignee: params.get("consignee") || "",
    currency: params.get("currency") || "",
    declarationNo: params.get("declarationNo") || "",
    route: route === "hk_transit" || route === "direct" ? route : "all",
    stage: stage && STAGES.includes(stage) ? stage : "all",
    exportFrom: params.get("exportFrom") || null,
    exportTo: params.get("exportTo") || null,
  };
}

/**
 * 报关应收汇：客户汇总与报关单明细共用筛选和一次后端结果，以页签切换。
 * 只读；登记回款、办资料、核对总账都跳到各自页面办理。
 */
export function ReceivablePanel() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "declarations" ? "declarations" : "customers";
  const filterParams = new URLSearchParams(params);
  filterParams.delete("view");
  filterParams.delete("detail");
  const filterKey = filterParams.toString();
  // 汇总/明细切换不重发请求；筛选和阶段变化以地址为准。
  const query = useMemo(() => readQuery(new URLSearchParams(filterKey)), [filterKey]);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);

  function update(change: (values: URLSearchParams) => void) {
    setParams(
      (current) => {
        const values = new URLSearchParams(current);
        change(values);
        return values;
      },
      { replace: true },
    );
  }

  function applyFilters(next: ReceivableQuery) {
    update((values) => {
      for (const name of FILTER_NAMES) {
        const value = next[name];
        if (value && value !== "all") values.set(name, value);
        else values.delete(name);
      }
    });
  }

  function drill(row: ReceivableCustomer) {
    update((values) => {
      values.set("view", "declarations");
      values.set("consignee", row.consignee);
      values.delete("stage");
    });
  }

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryReceivables(query, controller.signal);
        if (!controller.signal.aborted) setState({ kind: "ready", result });
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  const result = state.kind === "ready" ? state.result : null;
  const stageItems = (result?.stages ?? []).map((stage) => ({
    key: stage.stage,
    label: stage.label,
    count: stage.count,
  }));

  return (
    <>
      {result && <ReceivableStats totals={result.totals} />}
      <Card className="settlement-receivables">
        <CardHeader
          title="应收报关单"
          description={`客户汇总与报关单明细共用筛选条件；金额按海关回执成交总价，不同币种分开${
            result ? `；账龄截至 ${result.asOf}` : ""
          }。`}
          actions={<Link to={settlementReceiptPath(query.consignee)}>进入香港中转登记 →</Link>}
        />
        <div className="settlement-receivables__views">
          <Tabs
            label="报关应收汇展示方式"
            items={VIEWS}
            value={view}
            onChange={(next) => update((values) => values.set("view", next))}
          />
        </div>
        <FilterBar
          key={filterKey}
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            applyFilters({
              ...query,
              consignee: String(data.get("consignee") || "").trim(),
              declarationNo: String(data.get("declarationNo") || "").trim(),
              route: String(data.get("route") || "all") as RouteFilter,
              currency: String(data.get("currency") || "").trim(),
              exportFrom: String(data.get("exportFrom") || "") || null,
              exportTo: String(data.get("exportTo") || "") || null,
            });
          }}
          actions={
            <>
              <Button type="submit" variant="primary">
                查询
              </Button>
              <Button type="reset" onClick={() => applyFilters(EMPTY)}>
                重置
              </Button>
            </>
          }
        >
          <Field label="境外收货人" grow>
            <input name="consignee" defaultValue={query.consignee} placeholder="如 HONGKONG VISION" />
          </Field>
          <Field label="报关单号" grow>
            <input name="declarationNo" defaultValue={query.declarationNo} />
          </Field>
          <Field label="币种">
            <input name="currency" defaultValue={query.currency || ""} placeholder="如 USD" />
          </Field>
          <Field label="回款路径">
            <select name="route" defaultValue={query.route}>
              <option value="all">全部</option>
              <option value="hk_transit">香港中转</option>
              <option value="direct">直接收汇</option>
            </select>
          </Field>
          <Field label="出口日期 从">
            <input type="date" name="exportFrom" defaultValue={query.exportFrom || ""} />
          </Field>
          <Field label="至">
            <input type="date" name="exportTo" aria-label="出口日期 至" defaultValue={query.exportTo || ""} />
          </Field>
        </FilterBar>
        <CardContent flush>
          {state.kind === "loading" && (
            <Skeleton rows={3} label={view === "customers" ? "正在汇总客户应收汇" : "正在读取报关单明细"} />
          )}
          {state.kind === "error" && (
            <ErrorState
              title="报关应收汇读取失败"
              message={state.message}
              action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
            />
          )}
          {result &&
            (view === "customers" ? (
              result.customers.length ? (
                <ConsigneeSummary rows={result.customers} onDrill={drill} />
              ) : (
                <EmptyState
                  title="没有符合条件的报关单"
                  description="海关回执导入并匹配到 NS 报关单后出现在这里。"
                />
              )
            ) : (
              <>
                <div className="settlement-receivables__stages">
                  <Tabs
                    label="按结汇状态筛选报关单"
                    items={stageItems}
                    value={query.stage}
                    onChange={(stage) =>
                      update((values) => {
                        if (stage === "all") values.delete("stage");
                        else values.set("stage", stage);
                      })
                    }
                  />
                </div>
                {result.truncated && (
                  <Alert tone="warning">
                    符合条件的报关单共 {result.total} 张，下方只展示等待最久的 {result.items.length}{" "}
                    张；客户汇总与金额概况按全部筛选结果计算。请缩小查询范围查看其余报关单。
                  </Alert>
                )}
                {result.items.length ? (
                  <ReceivableTable rows={result.items} />
                ) : (
                  <EmptyState title="没有符合条件的报关单" description="请调整查询条件或结汇状态。" />
                )}
              </>
            ))}
        </CardContent>
      </Card>
    </>
  );
}
