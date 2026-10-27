import { Button } from "../../../shared/components/Button";
import type { MatchingSummary } from "../../matching/api";
import type { InvoiceRow } from "../types/invoice";
import type { useDetailRefresh } from "../hooks/useDetailRefresh";
import { money, shown } from "./format";
import "./invoice-status.css";

const tierLabels = { high: "高", medium: "中", low: "低", manual: "人工" } as const;
// 已匹配为成功色；未匹配与不参与比对为中性；部分匹配、待审核、待复核需要处理
const tone = (summary?: MatchingSummary) =>
  summary?.status === "confirmed"
    ? "success"
    : summary && summary.status !== "none" && summary.status !== "excluded"
      ? "warning"
      : "neutral";

export function InvoiceTable({
  rows,
  matching,
  matchingError,
  onMatch,
  onDetail,
  refresh,
}: {
  rows: InvoiceRow[];
  matching: Record<string, MatchingSummary>;
  matchingError: string;
  onMatch: (id: string) => void;
  onDetail: (id: string) => void;
  refresh?: ReturnType<typeof useDetailRefresh>;
}) {
  const pending = matchingError ? "读取失败" : "读取中…";
  return (
    <div
      className="invoice-list__table invoice-list__main-table"
      role="region"
      aria-label="进项发票列表，可横向滚动"
    >
      <table>
        <thead>
          <tr>
            {refresh && (
              <th scope="col">
                <input
                  type="checkbox"
                  aria-label="选择本页可补拉发票"
                  disabled={refresh.blocked || !rows.some((row) => refresh.actions[row.id]?.allowed)}
                  checked={
                    rows.some((row) => refresh.actions[row.id]?.allowed) &&
                    rows
                      .filter((row) => refresh.actions[row.id]?.allowed)
                      .every((row) => refresh.selected.includes(row.id))
                  }
                  onChange={(event) => refresh.selectAll(event.target.checked)}
                />
              </th>
            )}
            {[
              "发票号码 / 来源",
              "供应商 / 税号",
              "开票日期",
              "价税合计",
              "比对状态",
              "建议置信度",
              "导入时间（北京时间）",
              "票面状态",
              "操作",
            ].map((text) => (
              <th scope="col" key={text}>
                {text}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const summary = matching[row.id];
            return (
              <tr key={row.id}>
                {refresh && (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`选择发票${row.number}`}
                      title={refresh.actions[row.id]?.reason ?? "正在读取补拉权限"}
                      disabled={refresh.blocked || !refresh.actions[row.id]?.allowed}
                      checked={refresh.selected.includes(row.id)}
                      onChange={(event) => refresh.select(row.id, event.target.checked)}
                    />
                  </td>
                )}
                <td>
                  <b>{row.number}</b>
                  <small>
                    {row.source} · {shown(row.type)}
                  </small>
                </td>
                <td>
                  <b>{shown(row.seller)}</b>
                  <small>{shown(row.sellerTaxNo)}</small>
                </td>
                <td>{shown(row.date)}</td>
                <td className="invoice-list__amount">
                  {row.currency === "CNY" ? "¥ " : ""}
                  {money(row.gross)}
                  <small>税额 {money(row.tax)}</small>
                  <small>{row.currency}</small>
                </td>
                <td>
                  <span className={`invoice-list__match-state invoice-list__match-state--${tone(summary)}`}>
                    {summary ? summary.label : pending}
                  </span>
                  {summary && (
                    <small>
                      已通过 {summary.confirmed} 行 · 待审核 {summary.proposed} 条
                    </small>
                  )}
                </td>
                <td>{summary?.tier ? tierLabels[summary.tier] : "—"}</td>
                <td>{new Date(row.importedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</td>
                <td>
                  <span
                    className={`invoice-list__badge invoice-status-badge--${row.displayStatus ?? row.sourceStatus}`}
                  >
                    {row.status}
                  </span>
                </td>
                <td>
                  <Button
                    className="invoice-list__view"
                    onClick={() => onMatch(row.id)}
                    aria-label={`查看发票${row.number}的比对`}
                  >
                    比对
                  </Button>
                  <Button className="invoice-list__view" onClick={() => onDetail(row.id)}>
                    票面详情
                  </Button>
                  {refresh && (
                    <div>
                      <Button
                        className="invoice-list__view"
                        disabled={refresh.blocked || !refresh.actions[row.id]?.allowed}
                        title={refresh.actions[row.id]?.reason ?? "正在读取补拉权限"}
                        aria-label={
                          refresh.actions[row.id]?.allowed === false
                            ? `重新拉取商品明细（${refresh.actions[row.id]?.reason}）`
                            : undefined
                        }
                        onClick={() => void refresh.execute([row.id])}
                      >
                        重新拉取商品明细
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
