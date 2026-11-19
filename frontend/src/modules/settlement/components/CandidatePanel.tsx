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
import { queryCandidates, queryLedger } from "../api";
import type { Candidate, CandidateList, CandidateQuery, LedgerTotal, RouteFilter } from "../types";
import { ConsigneeSummary } from "./ConsigneeSummary";
import { CandidateTable } from "./CandidateTable";
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

const RECEIVABLE_VIEWS = [
  { key: "customers", label: "按客户汇总" },
  { key: "declarations", label: "报关单明细" },
] as const;

// 地址仅保存界面筛选状态，实际筛选、路径判定与金额汇总仍由后端处理。
function readReceivableQuery(params: URLSearchParams): CandidateQuery {
  const route = params.get("route");
  return {
    ...EMPTY,
    consignee: params.get("consignee") || "",
    declarationNo: params.get("declarationNo") || "",
    route: route === "hk_transit" || route === "direct" ? route : "all",
    exportFrom: params.get("exportFrom") || null,
    exportTo: params.get("exportTo") || null,
    batchStatus: "all",
  };
}

/**
 * 报关应收汇：客户汇总与报关单明细共用筛选和后端结果，以页签切换。
 * 应收页只读；香港中转待登记页复用查询、勾选与建批次流程。
 * 路径判定、能否建批次均由后端给出（handling、blockedReason），提交时后端再次校验。
 */
type CandidatePanelProps =
  | { mode: "receivables" }
  | {
      mode: "registration";
      consignee: string;
      onCreated: (batchId: number) => void;
    };

export function CandidatePanel(props: CandidatePanelProps) {
  const [params, setParams] = useSearchParams();
  const receivableView = params.get("view") === "declarations" ? "declarations" : "customers";
  const registration = props.mode === "registration";
  const initialQuery: CandidateQuery = {
    ...EMPTY,
    consignee: props.mode === "registration" ? props.consignee : "",
    route: registration ? "hk_transit" : "all",
    batchStatus: registration ? "unbatched" : "all",
  };
  const [registrationQuery, setRegistrationQuery] = useState<CandidateQuery>(initialQuery);
  const filterParams = new URLSearchParams(params);
  filterParams.delete("view");
  const filterKey = filterParams.toString();
  // 明细/汇总切换不改变查询对象；导航或刷新带来的筛选变化则以 URL 为准。
  const receivableQuery = useMemo(() => readReceivableQuery(new URLSearchParams(filterKey)), [filterKey]);
  const query = registration ? registrationQuery : receivableQuery;
  const [state, setState] = useState<State>({ kind: "loading" });
  const [directTotals, setDirectTotals] = useState<LedgerTotal[] | null>();
  const [selected, setSelected] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [refresh, setRefresh] = useState(0);

  function applyQuery(next: CandidateQuery) {
    if (registration) {
      setRegistrationQuery(next);
      return;
    }
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        for (const name of ["consignee", "declarationNo", "route", "exportFrom", "exportTo"] as const) {
          const value = next[name];
          if (value && value !== "all") updated.set(name, value);
          else updated.delete(name);
        }
        return updated;
      },
      { replace: true },
    );
  }

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryCandidates(query, controller.signal);
        if (!controller.signal.aborted) {
          setState({ kind: "ready", result });
          setSelected(result.suggestion ?? []);
        }
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  useEffect(() => {
    if (registration) return;
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
  }, [registration]);

  const toggle = (row: Candidate) =>
    setSelected((current) =>
      current.includes(row.declarationNo)
        ? current.filter((number) => number !== row.declarationNo)
        : [...current, row.declarationNo],
    );

  const failure = state.kind === "error" && (
    <ErrorState
      title={registration ? "待登记回款读取失败" : "报关应收汇读取失败"}
      message={state.message}
      action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
    />
  );

  return (
    <>
      {!registration && state.kind === "ready" && (
        <ReceivableStats
          combinedTotals={state.result.combinedTotals}
          totals={state.result.totals}
          unsettled={state.result.unsettled}
          directTotals={directTotals}
        />
      )}
      <Card className={!registration ? "settlement-receivables" : undefined}>
        <CardHeader
          title={registration ? "筛选待登记报关单" : "应收报关单"}
          description={
            registration
              ? "仅显示未建有效批次的香港中转报关单，勾选后登记香港到账。"
              : "客户汇总与报关单明细共用筛选条件；应收金额按海关回执成交总价统计，不同币种分开。"
          }
          actions={
            !registration && <Link to={settlementReceiptPath(query.consignee)}>进入香港中转登记 →</Link>
          }
        />
        {!registration && (
          <div className="settlement-receivables__views">
            <Tabs
              label="报关应收汇展示方式"
              items={RECEIVABLE_VIEWS}
              value={receivableView}
              onChange={(view) =>
                setParams(
                  (current) => {
                    const updated = new URLSearchParams(current);
                    updated.set("view", view);
                    return updated;
                  },
                  { replace: true },
                )
              }
            />
          </div>
        )}
        <FilterBar
          key={JSON.stringify(query)}
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            applyQuery({
              consignee: String(data.get("consignee") || "").trim(),
              declarationNo: String(data.get("declarationNo") || "").trim(),
              route: registration ? "hk_transit" : (String(data.get("route") || "all") as RouteFilter),
              batchStatus: registration ? "unbatched" : "all",
              exportFrom: String(data.get("exportFrom") || "") || null,
              exportTo: String(data.get("exportTo") || "") || null,
              targetAmount: registration ? String(data.get("targetAmount") || "").trim() : "",
            });
          }}
          actions={
            <>
              <Button type="submit" variant="primary">
                查询
              </Button>
              <Button type="reset" onClick={() => applyQuery(initialQuery)}>
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
          {!registration && (
            <Field label="回款路径">
              <select name="route" defaultValue={query.route}>
                <option value="all">全部</option>
                <option value="hk_transit">香港中转</option>
                <option value="direct">直接收汇</option>
              </select>
            </Field>
          )}
          <Field label="出口日期 从">
            <input type="date" name="exportFrom" defaultValue={query.exportFrom || ""} />
          </Field>
          <Field label="至">
            <input type="date" name="exportTo" aria-label="出口日期 至" defaultValue={query.exportTo || ""} />
          </Field>
          {registration && (
            <Field label="香港到账金额（到账 + 手续费）">
              <input
                name="targetAmount"
                inputMode="decimal"
                placeholder="推荐组合用"
                defaultValue={query.targetAmount}
              />
            </Field>
          )}
        </FilterBar>
        {registration ? (
          failure
        ) : (
          <CardContent flush>
            {state.kind === "loading" && (
              <Skeleton
                rows={3}
                label={receivableView === "customers" ? "正在汇总客户应收汇" : "正在读取报关单明细"}
              />
            )}
            {failure}
            {state.kind === "ready" &&
              (receivableView === "customers" ? (
                state.result.consignees.length ? (
                  <ConsigneeSummary rows={state.result.consignees} />
                ) : (
                  <EmptyState
                    title="没有符合条件的报关单"
                    description="海关回执导入并匹配到 NS 报关单后出现在这里。"
                  />
                )
              ) : (
                <>
                  {state.result.truncated && (
                    <Alert tone="warning">
                      符合条件的报关单共 {state.result.total} 张，下方只展示出口日期最近的{" "}
                      {state.result.items.length}{" "}
                      张；客户汇总与金额概况按全部筛选结果计算。请缩小查询范围查看其余报关单。
                    </Alert>
                  )}
                  {state.result.items.length ? (
                    <CandidateTable rows={state.result.items} />
                  ) : (
                    <EmptyState
                      title="没有符合条件的报关单"
                      description="请调整查询条件，或检查海关回执是否已导入并匹配到 NS 报关单。"
                    />
                  )}
                </>
              ))}
          </CardContent>
        )}
      </Card>
      {registration && state.kind !== "error" && (
        <Card>
          <CardHeader
            title="待登记回款"
            description="到账金额与手续费按银行水单填写，系统核对报关金额。"
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
                    {state.result.items.length} 张。请缩小查询条件查看其余报关单。
                  </Alert>
                )}
                {state.result.items.length ? (
                  <CandidateTable rows={state.result.items} selection={{ selected, onToggle: toggle }} />
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
      {props.mode === "registration" && creating && (
        <CreateBatchDialog
          declarationNos={selected}
          defaultAmount={query.targetAmount}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            setSelected([]);
            setRefresh((n) => n + 1);
            props.onCreated(id);
          }}
        />
      )}
    </>
  );
}
