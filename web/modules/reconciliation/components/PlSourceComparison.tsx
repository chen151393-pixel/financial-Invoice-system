import { Button } from "../../../shared/components/Button";
import { sourceColumns, type SourceComparisonState } from "../source-types";
import "./pl-source-comparison.css";

/** 只读联查页保留NS返回的平铺行顺序；不生成审核快照或推断父子关联。 */
export function PlSourceComparison({
  state,
  onRetry,
}: {
  state: SourceComparisonState;
  onRetry: () => void;
}) {
  if (state.kind !== "ready")
    return (
      <section
        className="pl-source-state"
        role={state.kind === "error" ? "alert" : "status"}
        aria-busy={state.kind === "loading"}
      >
        <h2>
          {state.kind === "idle"
            ? "查询采购与报关明细"
            : state.kind === "loading"
              ? "正在从 NS 查询…"
              : "查询失败"}
        </h2>
        <p>
          {state.kind === "error"
            ? state.message
            : state.kind === "idle"
              ? "输入 CD 编号、PL 单号或真实报关单号，查看 NS 来源对照。"
              : "正在读取完整来源数据，请稍候。"}
        </p>
        {state.kind === "error" && <Button onClick={onRetry}>重新查询</Button>}
      </section>
    );
  const { result } = state;
  const columns = result.contractVersion === 1 ? sourceColumns.slice(0, 15) : sourceColumns;
  return (
    <section className="pl-source">
      <div className="pl-source__summary" role="status">
        <strong>
          {result.counts.customs} 条报关行 · {result.counts.purchase} 条子采购行
        </strong>
        <span>
          查询条件：{result.query.pl || "未指定单号"}
          {result.query.month && ` · ${result.query.month}`}
          {result.query.createdFrom && ` · ${result.query.createdFrom} 至 ${result.query.createdTo}`}
        </span>
        <span>
          NS {result.account} · {new Date(result.readCompletedAt).toLocaleString("zh-CN")}
        </span>
      </div>
      {result.groups.length === 0 ? (
        <div className="pl-source-state">
          <h2>未找到对应单据</h2>
          <p>请调整查询条件后重试。</p>
        </div>
      ) : (
        result.groups.map((group) => (
          <article className="pl-source__group" key={group.id}>
            <h2>{group.title}</h2>
            <div
              className="pl-source__scroll"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 原生宽表需聚焦容器后用方向键滚动，沿用财务明细表的可访问性约定。
              tabIndex={0}
              role="region"
              aria-label={`${group.title}来源对照表，可横向滚动`}
            >
              <table>
                <caption>白色为报关来源行，浅蓝为采购来源行；按 NS 返回顺序展示。</caption>
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column} scope="col">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <tr
                      key={row.id}
                      className={`pl-source__row--${row.side}`}
                      aria-label={row.side === "customs" ? "报关来源行" : "子采购来源行"}
                    >
                      {columns.map((column, index) => (
                        <td
                          key={column}
                          className={[11, 13, 14, 15].includes(index) ? "pl-source__numeric" : undefined}
                        >
                          {row.cells[index] || "—"}
                          {row.missingCells.includes(index) && <small>来源缺失</small>}
                          {index === 14 && row.currency && <small>{row.currency}</small>}
                          {index === 5 && row.note && <small>{row.note}</small>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {group.warnings.length > 0 && (
              <ul className="pl-source__warnings" aria-label="来源提示">
                {group.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </article>
        ))
      )}
    </section>
  );
}
