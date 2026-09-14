import type { View } from "../types";

export function ReconcileCenter({ navigate }: { navigate: (view: View) => void }) {
  const rows = [
    {
      vendor: "深圳市华盛塑胶制品有限公司",
      invoice: "¥126,550.00",
      business: "¥126,550.00",
      bill: "¥126,550.00",
      diff: "¥0.00",
      status: "三方一致",
      tone: "success",
    },
    {
      vendor: "广州智创广告服务有限公司",
      invoice: "¥32,680.00",
      business: "¥31,400.00",
      bill: "¥31,400.00",
      diff: "+¥1,280.00",
      status: "发票偏高",
      tone: "danger",
    },
    {
      vendor: "深圳市跨速国际物流有限公司",
      invoice: "¥48,920.00",
      business: "—",
      bill: "—",
      diff: "+¥48,920.00",
      status: "缺业务单",
      tone: "warning",
    },
    {
      vendor: "东莞市优品包装科技有限公司",
      invoice: "¥89,600.00",
      business: "¥89,600.00",
      bill: "待回写",
      diff: "¥0.00",
      status: "待回写",
      tone: "info",
    },
  ];
  return (
    <>
      <div className="reconcile-summary">
        <article>
          <span>NetSuite 业务应付</span>
          <strong>¥21,532,000.00</strong>
          <small>PO / Item Receipt / Expense Report</small>
        </article>
        <i>⇄</i>
        <article>
          <span>柠檬云进项发票</span>
          <strong>¥18,264,300.00</strong>
          <small>已开票 2,846 张</small>
        </article>
        <i>⇄</i>
        <article>
          <span>NetSuite Vendor Bill</span>
          <strong>¥18,192,580.00</strong>
          <small>已入账 2,801 笔</small>
        </article>
        <div className="reconcile-result">
          <span>未开票 / 差异</span>
          <strong>¥3,267,700.00</strong>
          <small>47 项需要处理</small>
        </div>
      </div>
      <article className="panel table-panel">
        <div className="reconcile-toolbar">
          <div className="context-filters">
            <span>深圳主体</span>
            <span>CNY</span>
            <span>2026-08</span>
          </div>
          <div>
            <button className="tool-button">仅看差异</button>
            <button className="tool-button">导出对账单</button>
          </div>
        </div>
        <div className="table-wrap">
          <table className="data-table reconcile-table">
            <thead>
              <tr>
                <th>供应商</th>
                <th>柠檬云发票</th>
                <th>NS 业务应付</th>
                <th>NS Vendor Bill</th>
                <th>差异</th>
                <th>对账结论</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.vendor}>
                  <td>
                    <strong className="supplier-name">{row.vendor}</strong>
                  </td>
                  <td>{row.invoice}</td>
                  <td>{row.business}</td>
                  <td>{row.bill}</td>
                  <td>
                    <strong className={row.diff !== "¥0.00" ? "danger-text" : ""}>{row.diff}</strong>
                  </td>
                  <td>
                    <span className={`table-status ${row.tone}`}>
                      <i />
                      {row.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="link-button"
                      onClick={() =>
                        navigate(
                          row.status === "待回写"
                            ? "writeback"
                            : row.status === "三方一致"
                              ? "match"
                              : "exceptions",
                        )
                      }
                    >
                      查看明细
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}
