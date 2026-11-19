import { useEffect, useState } from "react";
import { Link } from "react-router";
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

/**
 * 报关应收汇：按境外收货人汇总应收汇并显示回款路径。
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
  const registration = props.mode === "registration";
  const initialQuery: CandidateQuery = {
    ...EMPTY,
    consignee: props.mode === "registration" ? props.consignee : "",
    route: registration ? "hk_transit" : "all",
    batchStatus: registration ? "unbatched" : "all",
  };
  const [query, setQuery] = useState<CandidateQuery>(initialQuery);
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
      <Card>
        <CardHeader
          title={registration ? "筛选待登记报关单" : "按境外收货人汇总"}
          description={
            registration
              ? "仅显示未建有效批次的香港中转报关单，勾选后登记香港到账。"
              : "应收汇金额为该收货人全部报关单的海关回执成交总价之和，按币种分开。"
          }
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setQuery({
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
              <Button type="reset" onClick={() => setQuery(initialQuery)}>
                重置
              </Button>
            </>
          }
        >
          <Field label="境外收货人" grow>
            <input name="consignee" defaultValue={initialQuery.consignee} placeholder="如 HONGKONG VISION" />
          </Field>
          <Field label="报关单号" grow>
            <input name="declarationNo" />
          </Field>
          {!registration && (
            <Field label="回款路径">
              <select name="route" defaultValue={EMPTY.route}>
                <option value="all">全部</option>
                <option value="hk_transit">香港中转</option>
                <option value="direct">直接收汇</option>
              </select>
            </Field>
          )}
          <Field label="出口日期 从">
            <input type="date" name="exportFrom" />
          </Field>
          <Field label="至">
            <input type="date" name="exportTo" aria-label="出口日期 至" />
          </Field>
          {registration && (
            <Field label="香港到账金额（到账 + 手续费）">
              <input name="targetAmount" inputMode="decimal" placeholder="推荐组合用" />
            </Field>
          )}
        </FilterBar>
        {registration ? (
          failure
        ) : (
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
        )}
      </Card>
      {state.kind !== "error" && (
        <Card>
          <CardHeader
            title={registration ? "待登记回款" : "报关单明细"}
            description={
              registration
                ? "到账金额与手续费按银行水单填写，系统核对报关金额。"
                : "查看报关应收与回款路径；香港回款请进入香港中转批次登记。"
            }
            actions={
              registration ? (
                <Button disabled={!selected.length} onClick={() => setCreating(true)}>
                  登记回款并建批次（{selected.length}）
                </Button>
              ) : (
                <Link to={settlementReceiptPath(query.consignee)}>进入香港中转登记 →</Link>
              )
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
                  <CandidateTable
                    rows={state.result.items}
                    selection={registration ? { selected, onToggle: toggle } : undefined}
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
