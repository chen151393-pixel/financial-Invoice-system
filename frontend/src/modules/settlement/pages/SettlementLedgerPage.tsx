import { useEffect, useState } from "react";
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
  StatCard,
  StatGrid,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { queryLedger } from "../api";
import { LedgerGroupTable } from "../components/LedgerGroupTable";
import type { LedgerList, LedgerQuery, LedgerStatusFilter } from "../types";
import "../components/settlement.css";

type State = { kind: "loading" } | { kind: "ready"; result: LedgerList } | { kind: "error"; message: string };

const INITIAL: LedgerQuery = { consignee: "", company: "", status: "all", page: 1, pageSize: 20 };

/**
 * 直接收汇明细（总账）：非香港中转的境外收货人按出口、收汇逐笔累计期末余额。
 * 余额、状态与合计全部来自后端；本页不做任何金额计算。
 */
export function SettlementLedgerPage() {
  const [query, setQuery] = useState<LedgerQuery>(INITIAL);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        setState({ kind: "ready", result: await queryLedger(query, controller.signal) });
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "加载失败，请稍后重试" });
      }
    }
    void load();
    return () => controller.abort();
  }, [query, refresh]);

  return (
    <div className="settlement-page">
      {state.kind === "ready" &&
        state.result.totals.map((total) => (
          <StatGrid key={total.currency} label={`${total.currency} 收汇概况`}>
            <StatCard
              glyph="出"
              label={`出口金额合计（${total.currency}）`}
              value={money(total.exportTotal)}
              note={`${total.exportCount} 票报关单 · ${total.consigneeCount} 家境外收货人`}
            />
            <StatCard
              glyph="收"
              tone="primary"
              label={`收汇金额合计（${total.currency}）`}
              value={money(total.receiptTotal)}
              note={`${total.receiptCount} 笔银行收汇`}
            />
            <StatCard
              glyph="余"
              tone="warning"
              label={`期末余额（${total.currency}）`}
              value={money(total.balance)}
              note={`未收 ${money(total.outstanding)} · 超收 ${money(total.overpaid)}`}
            />
          </StatGrid>
        ))}
      <Card>
        <CardHeader
          title="直接收汇明细"
          description="只含非香港中转的境外收货人；同一收货人按日期先后逐笔累计，出口加、收汇减，余额为负表示超收。"
        />
        <FilterBar
          embedded
          onSubmit={(form) => {
            const data = new FormData(form);
            setQuery({
              ...query,
              consignee: String(data.get("consignee") || "").trim(),
              company: String(data.get("company") || "").trim(),
              status: String(data.get("status") || "all") as LedgerStatusFilter,
              page: 1,
            });
          }}
          actions={
            <>
              <Button type="submit">查询</Button>
              <Button type="reset" variant="ghost" onClick={() => setQuery(INITIAL)}>
                清空
              </Button>
            </>
          }
        >
          <Field label="境外收货人">
            <input name="consignee" defaultValue={query.consignee} placeholder="按名称搜索" />
          </Field>
          <Field label="出口 / 收汇抬头">
            <input name="company" defaultValue={query.company} placeholder="如 上海毅鑫" />
          </Field>
          <Field label="期末余额">
            <select name="status" defaultValue={query.status}>
              <option value="all">全部</option>
              <option value="outstanding">有未收</option>
              <option value="settled">已收齐</option>
              <option value="overpaid">超收</option>
            </select>
          </Field>
        </FilterBar>
        <CardContent flush>
          {state.kind === "loading" && <Skeleton rows={5} label="正在读取直接收汇明细" />}
          {state.kind === "error" && (
            <ErrorState
              title="直接收汇明细读取失败"
              message={state.message}
              action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
            />
          )}
          {state.kind === "ready" && (
            <>
              {state.result.skipped.length > 0 && (
                <Alert tone="warning" title={`${state.result.skipped.length} 张直接收汇报关单未计入`}>
                  {state.result.skipped.map((item) => `${item.declarationNo}（${item.reason}）`).join("；")}
                </Alert>
              )}
              {state.result.groups.length ? (
                state.result.groups.map((group) => (
                  <LedgerGroupTable key={`${group.consignee}|${group.currency}`} group={group} />
                ))
              ) : (
                <EmptyState
                  title="没有符合条件的直接收汇明细"
                  description="判定为直接收汇的报关单和银行收汇明细中的收汇记录出现在这里。"
                />
              )}
            </>
          )}
        </CardContent>
        {state.kind === "ready" && state.result.total > 0 && (
          <CardFooter>
            <Pagination
              label="直接收汇明细分页"
              total={state.result.total}
              unit="家"
              page={state.result.page}
              pageCount={Math.max(1, Math.ceil(state.result.total / state.result.pageSize))}
              pageSize={query.pageSize}
              pageSizes={[20, 50]}
              onPageChange={(page) => setQuery({ ...query, page })}
              onPageSizeChange={(pageSize) => setQuery({ ...query, pageSize, page: 1 })}
            />
          </CardFooter>
        )}
      </Card>
    </div>
  );
}
