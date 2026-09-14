import { useMemo, useState } from "react";
import { invoices } from "../fixtures";
import { SourceHealth } from "../components/SourceHealth";
import type { View } from "../types";

const statuses = ["全部", "已匹配", "待确认", "待匹配", "异常", "待回写", "已回写"] as const;

export function InvoiceList({ navigate }: { navigate: (view: View) => void }) {
  const [filter, setFilter] = useState<(typeof statuses)[number]>("全部");
  const [query, setQuery] = useState("");
  // 仅筛选本地演示样本；正式业务列表的筛选和统计由后端负责。
  const searchedInvoices = useMemo(
    () =>
      invoices.filter(
        (row) => row.supplier.includes(query) || row.no.includes(query) || row.vendorId.includes(query),
      ),
    [query],
  );
  const visibleInvoices = searchedInvoices.filter((row) => filter === "全部" || row.status === filter);
  function clearFilters() {
    setQuery("");
    setFilter("全部");
  }
  return (
    <>
      <SourceHealth navigate={navigate} />
      <div className="mini-stat-grid">
        <div>
          <span>价税合计</span>
          <strong>¥ 18,264,300.00</strong>
          <small>全量模拟概览 · 2,846 张发票</small>
        </div>
        <div>
          <span>可抵扣税额</span>
          <strong>¥ 1,857,420.18</strong>
          <small>认证率 91.6%</small>
        </div>
        <div>
          <span>待匹配金额</span>
          <strong>¥ 1,246,870.00</strong>
          <small>98 张待处理</small>
        </div>
        <div>
          <span>异常金额</span>
          <strong className="danger-text">¥ 321,860.00</strong>
          <small>47 张异常票</small>
        </div>
      </div>
      <article className="panel table-panel">
        <div className="list-tabs">
          {statuses.map((tab) => (
            <button
              className={filter === tab ? "active" : ""}
              aria-pressed={filter === tab}
              onClick={() => setFilter(tab)}
              key={tab}
            >
              {tab} {searchedInvoices.filter((row) => tab === "全部" || row.status === tab).length}
            </button>
          ))}
        </div>
        <div className="table-tools">
          <label className="search-box">
            <span>⌕</span>
            <input
              aria-label="搜索发票"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索发票 / 供应商 / NS ID"
            />
          </label>
          <div>
            <button className="tool-button">主体⌄</button>
            <button className="tool-button">会计期间⌄</button>
            <button className="tool-button">币种⌄</button>
            <button className="tool-button">匹配关系⌄</button>
            <button className="tool-button">⊙ 更多筛选</button>
          </div>
        </div>
        <div className="table-context">
          <span>主体：深圳市新思跨境电子商务有限公司</span>
          <span>币种：CNY</span>
          <span>期间：2026-08</span>
          <span>汇率：1.0000</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" aria-label="全选" />
                </th>
                <th>发票号码 / 来源</th>
                <th>供应商 / NS Internal ID</th>
                <th>开票日期</th>
                <th>价税合计</th>
                <th>关联方式</th>
                <th>置信度</th>
                <th>同步批次 / 新鲜度</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleInvoices.length === 0 && (
                <tr>
                  <td colSpan={10}>
                    <div className="invoice-list-empty">
                      <p role="status">未找到匹配发票，请调整搜索词或状态筛选。</p>
                      <button className="button secondary" onClick={clearFilters}>
                        清除筛选
                      </button>
                    </div>
                  </td>
                </tr>
              )}
              {visibleInvoices.map((row) => (
                <tr key={row.no}>
                  <td>
                    <input type="checkbox" aria-label={`选择发票 ${row.no}`} />
                  </td>
                  <td>
                    <strong className="invoice-number">{row.no}</strong>
                    <span className="source-line">
                      <i />
                      柠檬云 · 增值税专票
                    </span>
                  </td>
                  <td>
                    <strong className="supplier-name">{row.supplier}</strong>
                    <span>{row.vendorId}</span>
                  </td>
                  <td>{row.date}</td>
                  <td>
                    <strong>{row.amount}</strong>
                    <span>税额 {row.tax}</span>
                  </td>
                  <td>
                    <span className="relation-badge">{row.relation}</span>
                  </td>
                  <td>
                    <div
                      className={`confidence ${row.confidence >= 90 ? "good" : row.confidence >= 60 ? "fair" : "poor"}`}
                    >
                      <b>{row.confidence}%</b>
                      <span>
                        <i style={{ width: `${row.confidence}%` }} />
                      </span>
                    </div>
                  </td>
                  <td>
                    <strong className="batch-id">{row.batch}</strong>
                    <span>{row.freshness}</span>
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
                      onClick={() => navigate(row.status === "异常" ? "exceptions" : "match")}
                    >
                      {row.status === "异常" ? "处理" : "查看"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <span role="status">共 {visibleInvoices.length} 条匹配结果</span>
          <span>演示样本共 {invoices.length} 条 · 匹配结果已全部展示</span>
        </div>
      </article>
    </>
  );
}
