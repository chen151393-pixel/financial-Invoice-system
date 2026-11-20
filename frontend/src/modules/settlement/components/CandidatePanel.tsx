import { useEffect, useState } from "react";
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
import { queryCandidates } from "../api";
import type { Candidate, CandidateList, CandidateQuery } from "../types";
import { CandidateTable } from "./CandidateTable";
import { CreateBatchDialog } from "./CreateBatchDialog";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: CandidateList }
  | { kind: "error"; message: string };

const EMPTY: CandidateQuery = {
  consignee: "",
  declarationNo: "",
  route: "hk_transit",
  batchStatus: "unbatched",
  exportFrom: null,
  exportTo: null,
  targetAmount: "",
};

/**
 * 香港中转待登记回款：查询未建有效批次的香港中转报关单，勾选后登记一条香港到账流水建批次。
 * 能否选入批次由后端给出（handling、blockedReason），提交时后端再次校验。
 * 报关应收汇的客户汇总与报关单明细见 ReceivablePanel。
 */
export function CandidatePanel({
  consignee,
  onCreated,
}: {
  consignee: string;
  onCreated: (batchId: number) => void;
}) {
  const initialQuery: CandidateQuery = { ...EMPTY, consignee };
  const [query, setQuery] = useState<CandidateQuery>(initialQuery);
  const [state, setState] = useState<State>({ kind: "loading" });
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

  const toggle = (row: Candidate) =>
    setSelected((current) =>
      current.includes(row.declarationNo)
        ? current.filter((number) => number !== row.declarationNo)
        : [...current, row.declarationNo],
    );

  return (
    <>
      <Card>
        <CardHeader
          title="筛选待登记报关单"
          description="仅显示未建有效批次的香港中转报关单，勾选后登记香港到账。"
        />
        <FilterBar
          key={JSON.stringify(query)}
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setQuery({
              ...EMPTY,
              consignee: String(data.get("consignee") || "").trim(),
              declarationNo: String(data.get("declarationNo") || "").trim(),
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
              <Button type="reset" onClick={() => setQuery(initialQuery)}>
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
          <Field label="出口日期 从">
            <input type="date" name="exportFrom" defaultValue={query.exportFrom || ""} />
          </Field>
          <Field label="至">
            <input type="date" name="exportTo" aria-label="出口日期 至" defaultValue={query.exportTo || ""} />
          </Field>
          <Field label="香港到账金额（到账 + 手续费）">
            <input
              name="targetAmount"
              inputMode="decimal"
              placeholder="推荐组合用"
              defaultValue={query.targetAmount}
            />
          </Field>
        </FilterBar>
        {state.kind === "error" && (
          <ErrorState
            title="待登记回款读取失败"
            message={state.message}
            action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
          />
        )}
      </Card>
      {state.kind !== "error" && (
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
