import { useId } from "react";
import { Button } from "../../../shared/components/Button";
import { comparisonColumns, type ComparisonGroup, type ComparisonRow, type ComparisonState } from "../types";
import "./pl-comparison.css";

function SourceRows({ rows, source }: { rows: readonly ComparisonRow[]; source: "customs" | "purchase" }) {
  const label = source === "customs" ? "报关明细" : "子采购订单明细";
  return (
    <>
      <tr className={`pl-comparison__source pl-comparison__source--${source}`}>
        <th colSpan={15} scope="rowgroup">
          {label}
        </th>
      </tr>
      {rows.length === 0 ? (
        <tr>
          <td colSpan={15} className="pl-comparison__missing">
            本组暂无{label}，请核实 PL 与公司关联。
          </td>
        </tr>
      ) : (
        rows.map((row) => (
          <tr key={row.id}>
            {row.cells.map((value, index) => (
              <td
                key={comparisonColumns[index]}
                className={
                  index === 13
                    ? "pl-comparison__pending"
                    : index === 11 || index === 14
                      ? "pl-comparison__numeric"
                      : undefined
                }
              >
                {value || "—"}
                {index === 14 && value && (
                  <small className="pl-comparison__currency">{row.currency || "未返回币种"}</small>
                )}
              </td>
            ))}
          </tr>
        ))
      )}
    </>
  );
}

function ComparisonTable({ group }: { group: ComparisonGroup }) {
  const headingId = useId();
  return (
    <article className="pl-comparison__group" aria-labelledby={headingId}>
      <div className="pl-comparison__group-head">
        <div>
          <h2 id={headingId}>
            {group.pl}
            <span>{group.company}</span>
          </h2>
          <p>{group.summary}</p>
        </div>
        <span className="pl-comparison__status">{group.status}</span>
      </div>
      <div
        className="pl-comparison__scroll"
        role="region"
        aria-label={`${group.pl} ${group.company}对照表，可横向滚动`}
      >
        <table>
          <caption className="pl-comparison__sr-only">
            {group.company}：同组报关明细在上，采购明细在下。
          </caption>
          <thead>
            <tr>
              {comparisonColumns.map((column) => (
                <th scope="col" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <SourceRows rows={group.customs} source="customs" />
          </tbody>
          <tbody>
            <SourceRows rows={group.purchases} source="purchase" />
          </tbody>
        </table>
      </div>
    </article>
  );
}

/** 仅展示后端查询结果，Excel直接使用该次响应中的文件，不重新读取或汇总。 */
export function PlComparison({ state, onRetry }: { state: ComparisonState; onRetry: () => void }) {
  return (
    <div className="pl-comparison" aria-busy={state.kind === "loading"}>
      {state.kind === "ready" ? (
        <>
          <div className="pl-comparison__toolbar">
            <div className="pl-comparison__snapshot">
              <strong>
                查询结果 · {state.result.pl} · {state.result.company || "全部公司"}
              </strong>
              <span>
                NS 实时记录 · {state.result.account} ·{" "}
                {new Date(state.result.queriedAt).toLocaleString("zh-CN")}
              </span>
            </div>
            {state.result.download && (
              <a
                className="pl-comparison__download"
                href={`data:${state.result.download.mediaType};base64,${state.result.download.contentBase64}`}
                download={state.result.download.filename}
              >
                导出 Excel
              </a>
            )}
          </div>
          {state.result.groups.length ? (
            state.result.groups.map((group) => <ComparisonTable key={group.id} group={group} />)
          ) : (
            <div className="pl-comparison__state" role="status">
              <h2>未找到对应的采购或报关明细</h2>
              <p>请核实 PL 单号和申报公司，或留空公司后重新查询。</p>
            </div>
          )}
          {state.result.warnings.length > 0 && (
            <ul className="pl-comparison__warnings" aria-label="数据提示">
              {state.result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          {state.result.groups.length > 0 && (
            <p className="pl-comparison__help">
              含税单价统一待确认。金额按来源币种保留；导出包含当前查询的合并核对及来源明细。
            </p>
          )}
        </>
      ) : (
        <div className="pl-comparison__state" role={state.kind === "error" ? "alert" : "status"}>
          <h2>
            {state.kind === "loading"
              ? "正在从 NS 拉取采购与报关明细…"
              : state.kind === "idle"
                ? "按 PL 查找需要核对的单据"
                : "拉取失败"}
          </h2>
          <p>
            {state.kind === "loading"
              ? "完整读取后展示结果，请稍候。"
              : state.kind === "idle"
                ? "填写上方查询条件，报关明细在上、子采购订单明细在下展示。"
                : state.message}
          </p>
          {state.kind === "error" && (
            <Button variant="secondary" onClick={onRetry}>
              重新拉取
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
