import { useEffect, useState } from "react";
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
import { queryCandidates } from "../api";
import type { Candidate, CandidateList, CandidateQuery, RouteFilter } from "../types";
import { CreateBatchDialog } from "./CreateBatchDialog";

type State =
  | { kind: "loading" }
  | { kind: "ready"; result: CandidateList }
  | { kind: "error"; message: string };

const EMPTY: CandidateQuery = { consignee: "", declarationNo: "", route: "all", targetAmount: "" };

/** 可结汇报关单：按境外收货人筛选、按到账金额推荐组合，勾选后登记回款建批次。 */
export function CandidatePanel({ onCreated }: { onCreated: (batchId: number) => void }) {
  const [query, setQuery] = useState<CandidateQuery>(EMPTY);
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
      render: (row) => (
        <input
          type="checkbox"
          aria-label={`选择报关单 ${row.declarationNo}`}
          checked={selected.includes(row.declarationNo)}
          disabled={Boolean(row.blockedReason)}
          onChange={() => toggle(row)}
        />
      ),
    },
    {
      key: "number",
      header: "报关单号 / CD",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{row.declarationNo}</strong>
          <span>{row.recordNo || "—"}</span>
        </div>
      ),
    },
    { key: "orders", header: "销售订单", render: (row) => row.salesOrders.join("、") || "—" },
    { key: "consignee", header: "境外收货人", render: (row) => row.consignee || "—" },
    { key: "date", header: "出口日期", render: (row) => row.exportDate || "—" },
    {
      key: "route",
      header: "回款路径",
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
      render: (row) => (row.amount ? `${row.currency} ${money(row.amount)}` : "—"),
    },
    {
      key: "state",
      header: "状态",
      render: (row) =>
        row.blockedReason ? (
          <Badge tone="warning">{row.blockedReason}</Badge>
        ) : (
          <Badge tone="success">可结汇</Badge>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader
        title="待结汇报关单"
        description="报关金额取海关回执成交总价。按收款金额（到账 + 手续费）可自动推荐金额恰好吻合的报关单组合。"
        actions={
          <Button disabled={!selected.length} onClick={() => setCreating(true)}>
            登记回款并建批次（{selected.length}）
          </Button>
        }
      />
      <FilterBar
        embedded
        onSubmit={(form) => {
          const data = new FormData(form);
          setQuery({
            consignee: String(data.get("consignee") || "").trim(),
            declarationNo: String(data.get("declarationNo") || "").trim(),
            route: String(data.get("route") || "all") as RouteFilter,
            targetAmount: String(data.get("targetAmount") || "").trim(),
          });
        }}
        actions={
          <>
            <Button type="submit">查询</Button>
            <Button type="reset" variant="ghost" onClick={() => setQuery(EMPTY)}>
              清空
            </Button>
          </>
        }
      >
        <Field label="境外收货人">
          <input name="consignee" defaultValue={query.consignee} placeholder="如 HONGKONG VISION" />
        </Field>
        <Field label="报关单号">
          <input name="declarationNo" defaultValue={query.declarationNo} />
        </Field>
        <Field label="回款路径">
          <select name="route" defaultValue={query.route}>
            <option value="all">全部</option>
            <option value="hk_transit">香港中转</option>
            <option value="direct">直接收汇</option>
          </select>
        </Field>
        <Field label="收款金额（到账 + 手续费）">
          <input
            name="targetAmount"
            inputMode="decimal"
            defaultValue={query.targetAmount}
            placeholder="推荐组合用"
          />
        </Field>
      </FilterBar>
      <CardContent flush>
        {state.kind === "loading" && <Skeleton rows={4} label="正在读取待结汇报关单" />}
        {state.kind === "error" && (
          <ErrorState
            title="待结汇报关单读取失败"
            message={state.message}
            action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
          />
        )}
        {state.kind === "ready" && (
          <>
            {state.result.suggestionNote && (
              <Alert tone={state.result.suggestion ? "success" : "info"}>{state.result.suggestionNote}</Alert>
            )}
            {state.result.items.length ? (
              <DataTable
                label="待结汇报关单"
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
    </Card>
  );
}
