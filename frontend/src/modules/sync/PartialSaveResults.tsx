import type { PullResult } from "./api";

const statuses = {
  saved: "已保存",
  failed: "失败，未保存",
  unknown: "保存结果待核实",
  not_processed: "未处理",
};

export function PartialSaveResults({ batch }: { batch: NonNullable<PullResult["batch"]> }) {
  return (
    <section className="sync-page__save-results" aria-label="本批逐单保存结果">
      <p className="sync-page__scope-change">
        已保存 {batch.counts.saved} 张，失败 {batch.counts.failed} 张，待核实 {batch.counts.unknown}{" "}
        张，未处理 {batch.counts.not_processed} 张（按本批入口单据计数）。
        同一报关单及关联子采购一起保存，失败组保留原有本地数据。失败原因处理后可重新拉取；结果待核实时先核实本地记录。
      </p>
      <div className="sync-page__table" role="region" aria-label="逐单保存结果表格，可横向滚动">
        <table>
          <caption>本批逐单保存结果</caption>
          <thead>
            <tr>
              <th scope="col">单据编号</th>
              <th scope="col">内部编号</th>
              <th scope="col">保存状态</th>
              <th scope="col">处理说明</th>
            </tr>
          </thead>
          <tbody>
            {batch.items.map((item) => (
              <tr key={item.id}>
                <td>{item.number}</td>
                <td>{item.id}</td>
                <td>{statuses[item.status]}</td>
                <td>{item.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
