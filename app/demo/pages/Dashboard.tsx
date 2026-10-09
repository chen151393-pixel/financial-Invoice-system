import { kpis, tasks } from "../fixtures";
import { SourceHealth } from "../components/SourceHealth";
import type { View } from "../types";

export function Dashboard({ navigate }: { navigate: (view: View) => void }) {
  return (
    <>
      <SourceHealth navigate={navigate} />
      <div className="period-bar">
        <div className="period-tabs">
          <button className="selected">本月</button>
          <button>上月</button>
          <button>本季度</button>
          <button>自定义</button>
        </div>
        <div className="context-filters">
          <span>深圳主体</span>
          <span>CNY 人民币</span>
          <span>会计期间 2026-08</span>
        </div>
      </div>
      <div className="kpi-grid">
        {kpis.map((item) => (
          <article className={`kpi-card ${item.tone}`} key={item.label}>
            <div className="kpi-title">
              <span>{item.label}</span>
              <b>↗</b>
            </div>
            <div className="kpi-value">
              {item.value}
              <small>{item.unit}</small>
            </div>
            <div className="kpi-note">
              <i />
              {item.note}
            </div>
          </article>
        ))}
      </div>
      <div className="dashboard-grid">
        <article className="panel invoice-progress">
          <div className="panel-head">
            <div>
              <h2>开票进度</h2>
              <p>按 NetSuite 业务应付金额统计</p>
            </div>
            <button className="text-button" onClick={() => navigate("reconcile")}>
              查看系统对账 →
            </button>
          </div>
          <div className="progress-summary">
            <div>
              <span>应开票总额</span>
              <strong>¥ 2,153.2万</strong>
            </div>
            <div className="legend">
              <span>
                <i className="green-dot" />
                已开票 84.8%
              </span>
              <span>
                <i className="gray-dot" />
                未开票 15.2%
              </span>
            </div>
          </div>
          <div className="progress-track">
            <span />
          </div>
          <div className="bar-chart" aria-label="近六个月开票趋势">
            {[72, 81, 67, 90, 78, 94].map((h, i) => (
              <div className="bar-group" key={i}>
                <div className="bar-bg">
                  <span style={{ height: `${h}%` }} />
                </div>
                <b>{["3月", "4月", "5月", "6月", "7月", "8月"][i]}</b>
              </div>
            ))}
          </div>
        </article>
        <article className="panel match-panel">
          <div className="panel-head">
            <div>
              <h2>自动匹配概览</h2>
              <p>柠檬云发票 ↔ NetSuite 业务单据</p>
            </div>
            <span className="status-badge">规则引擎运行中</span>
          </div>
          <div className="donut-row">
            <div className="donut">
              <div>
                <strong>94.9%</strong>
                <span>整体匹配率</span>
              </div>
            </div>
            <div className="match-stats">
              <div>
                <i className="match high" />
                <span>
                  高置信匹配<small>≥ 90%</small>
                </span>
                <strong>2,532</strong>
              </div>
              <div>
                <i className="match mid" />
                <span>
                  需人工确认<small>60%–89%</small>
                </span>
                <strong>169</strong>
              </div>
              <div>
                <i className="match low" />
                <span>
                  待匹配<small>&lt; 60%</small>
                </span>
                <strong>98</strong>
              </div>
            </div>
          </div>
        </article>
      </div>
      <article className="panel task-panel">
        <div className="panel-head">
          <div>
            <h2>今日待处理</h2>
            <p>异常池 · 按风险、金额与关账影响排序</p>
          </div>
          <button className="text-button" onClick={() => navigate("exceptions")}>
            进入异常池 →
          </button>
        </div>
        <div className="task-list">
          {tasks.map((task) => (
            <div className="task-row" key={task.label}>
              <span className={`severity ${task.level}`} />
              <div className="task-name">
                <strong>{task.label}</strong>
                <span>
                  {task.count} 张 · 责任组：{task.owner}
                </span>
              </div>
              <strong className="task-amount">{task.amount}</strong>
              <button onClick={() => navigate(task.label.includes("回写") ? "writeback" : "exceptions")}>
                立即处理
              </button>
            </div>
          ))}
        </div>
      </article>
    </>
  );
}
