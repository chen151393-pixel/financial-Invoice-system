import type { PullResult } from "./api";
import { PartialSaveResults } from "./PartialSaveResults";

export function PullResults({ result }: { result: PullResult }) {
  return (
    <>
      <p className="sync-page__applied-range">
        本次结果 · {result.dateRange.label}：
        {result.dateRange.startDate
          ? `${result.dateRange.startDate} 至 ${result.dateRange.endDate}（含起止当天）`
          : "不限日期"}
      </p>
      <p role="status" className="sync-page__result-summary">
        {result.message} · 本批 {result.count} 张 ·{" "}
        {new Date(result.pulledAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}（北京时间）
      </p>
      {result.batch && <PartialSaveResults batch={result.batch} />}
      {result.storage && (
        <div role="status" className="sync-page__result-summary">
          {result.storage.savedAt ? (
            <p>
              最近成功保存时间：
              {new Date(result.storage.savedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
              （北京时间）
            </p>
          ) : (
            <p>本批暂无确认成功的保存记录。</p>
          )}
          <p>
            采购单：新增 {result.storage.purchase.created} 张，更新 {result.storage.purchase.updated}{" "}
            张；明细新增 {result.storage.purchase.linesCreated} 行，更新{" "}
            {result.storage.purchase.linesUpdated} 行。
          </p>
          <p>
            报关单（含关联单据）：新增 {result.storage.customs.created} 张，更新{" "}
            {result.storage.customs.updated} 张；明细新增 {result.storage.customs.linesCreated} 行，更新{" "}
            {result.storage.customs.linesUpdated} 行。
          </p>
          {result.storage.relations && (
            <p>
              关联依据：{result.storage.relations.collected} 张已读取，{result.storage.relations.partial}{" "}
              张待补齐； 原始报关行 {result.storage.relations.rawLines} 条，装箱明细{" "}
              {result.storage.relations.packingLines} 条， 销售与采购行关系{" "}
              {result.storage.relations.purchaseLinks} 条。读取依据不代表审核通过。
            </p>
          )}
          {result.storage.warnings?.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
      {result.count === 0 ? (
        <div className="sync-page__empty">
          <strong>本批没有单据</strong>
          <p>该批次未返回单据，可查看其他已完成批次或调整日期重新拉取。</p>
        </div>
      ) : (
        <div className="sync-page__table">
          <table>
            <thead>
              <tr>
                <th>内部编号</th>
                <th>单据编号</th>
                <th>单据详情</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.number}</td>
                  <td>
                    <details>
                      <summary>查看原始字段</summary>
                      <pre>{JSON.stringify(row.record, null, 2)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
