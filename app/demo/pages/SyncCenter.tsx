import { syncJobs } from "../fixtures";

export function SyncCenter({ notify }: { notify: (message: string) => void }) {
  return (
    <>
      <div className="connector-grid">
        <article className="connector-card">
          <div>
            <i className="system-logo ns">N</i>
            <span>
              <strong>NetSuite Sandbox</strong>
              <small>OAuth 2.0 M2M · SuiteTalk REST</small>
            </span>
          </div>
          <span className="connector-state healthy">连接正常</span>
          <dl>
            <div>
              <dt>最后成功</dt>
              <dd>10:26:42</dd>
            </div>
            <div>
              <dt>同步游标</dt>
              <dd>lastModified 10:24</dd>
            </div>
            <div>
              <dt>今日记录</dt>
              <dd>18,462</dd>
            </div>
            <div>
              <dt>失败任务</dt>
              <dd className="danger-text">1</dd>
            </div>
          </dl>
          <button
            className="button outline-primary"
            onClick={() => notify("NetSuite 增量同步已启动：NS-0825-1036")}
          >
            立即增量同步
          </button>
        </article>
        <article className="connector-card">
          <div>
            <i className="system-logo lemon">柠</i>
            <span>
              <strong>柠檬云发票</strong>
              <small>OpenAPI · 发票 + 原始附件</small>
            </span>
          </div>
          <span className="connector-state healthy">连接正常</span>
          <dl>
            <div>
              <dt>最后成功</dt>
              <dd>10:28:17</dd>
            </div>
            <div>
              <dt>同步游标</dt>
              <dd>updateTime 10:20</dd>
            </div>
            <div>
              <dt>今日发票</dt>
              <dd>186</dd>
            </div>
            <div>
              <dt>失败任务</dt>
              <dd>0</dd>
            </div>
          </dl>
          <button
            className="button outline-primary"
            onClick={() => notify("柠檬云增量同步已启动：LY-0825-1036")}
          >
            立即增量同步
          </button>
        </article>
        <article className="connector-card pipeline">
          <div>
            <i className="system-logo engine">⇄</i>
            <span>
              <strong>对账数据管道</strong>
              <small>标准化 → 匹配 → 异常 → 回写</small>
            </span>
          </div>
          <span className="connector-state attention">3 项待处理</span>
          <div className="pipeline-steps">
            <b>拉取</b>
            <i>→</i>
            <b>清洗</b>
            <i>→</i>
            <b>匹配</b>
            <i>→</i>
            <b>审批</b>
            <i>→</i>
            <b>回写</b>
          </div>
          <p>每 10 分钟增量同步；每日 02:00 执行全量校验。</p>
          <button className="button secondary" onClick={() => notify("已重新计算最近一次对账批次")}>
            重算最近批次
          </button>
        </article>
      </div>
      <article className="panel sync-table">
        <div className="panel-head">
          <div>
            <h2>同步任务记录</h2>
            <p>所有时间为 Asia/Shanghai · 失败任务可安全重试</p>
          </div>
          <button className="tool-button">导出日志</button>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>数据源</th>
                <th>任务</th>
                <th>批次号</th>
                <th>记录数</th>
                <th>完成时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {syncJobs.map((job) => (
                <tr key={job.batch}>
                  <td>
                    <strong>{job.system}</strong>
                  </td>
                  <td>{job.job}</td>
                  <td>
                    <strong className="batch-id">{job.batch}</strong>
                  </td>
                  <td>{job.records}</td>
                  <td>{job.time}</td>
                  <td>
                    <span className={`table-status ${job.tone}`}>
                      <i />
                      {job.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="link-button"
                      onClick={() =>
                        notify(job.status === "部分失败" ? "失败的 1 条记录已加入重试队列" : "已打开同步明细")
                      }
                    >
                      {job.status === "部分失败" ? "重试" : "查看"}
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
