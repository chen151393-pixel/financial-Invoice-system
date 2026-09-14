import { useState } from "react";

export function WritebackCenter({ notify }: { notify: (message: string) => void }) {
  const [tab, setTab] = useState("待回写 12");
  const jobs = [
    {
      id: "WB-202608-00482",
      invoice: "244420...54321",
      object: "Vendor Bill ID 99842",
      content: "匹配关系 + 发票号码 + 附件链接",
      user: "陈静",
      time: "10:31",
      status: "等待审批",
      tone: "warning",
    },
    {
      id: "WB-202608-00481",
      invoice: "244420...54287",
      object: "Vendor Bill ID 99839",
      content: "一单多票累计金额 + 发票明细",
      user: "系统",
      time: "10:25",
      status: "队列中",
      tone: "info",
    },
    {
      id: "WB-202608-00476",
      invoice: "244420...53653",
      object: "Vendor Bill ID 99798",
      content: "匹配状态 + 可抵扣税额",
      user: "陈静",
      time: "09:48",
      status: "已成功",
      tone: "success",
    },
    {
      id: "WB-202608-00472",
      invoice: "244420...53219",
      object: "Vendor Bill ID 99766",
      content: "发票号码 + 关联明细",
      user: "系统",
      time: "09:21",
      status: "失败",
      tone: "danger",
    },
  ];
  return (
    <>
      <div className="writeback-banner">
        <div>
          <span>安全回写策略</span>
          <h2>先审批、后入队；API 成功后才更新业务状态</h2>
          <p>采用幂等键避免重复写入，所有请求保留操作者、时间、对象、结果与 Trace ID。</p>
        </div>
        <div>
          <strong>12</strong>
          <span>待回写</span>
        </div>
        <div>
          <strong>3</strong>
          <span>失败待重试</span>
        </div>
        <div>
          <strong>99.6%</strong>
          <span>今日成功率</span>
        </div>
      </div>
      <article className="panel table-panel">
        <div className="list-tabs">
          {["待回写 12", "处理中 4", "已成功 2,785", "失败 3", "操作日志"].map((item) => (
            <button className={tab === item ? "active" : ""} onClick={() => setTab(item)} key={item}>
              {item}
            </button>
          ))}
        </div>
        <div className="table-wrap">
          <table className="data-table writeback-table">
            <thead>
              <tr>
                <th>回写任务 / Trace ID</th>
                <th>发票</th>
                <th>NetSuite 对象</th>
                <th>回写内容</th>
                <th>发起人 / 时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, index) => (
                <tr key={job.id}>
                  <td>
                    <strong className="invoice-number">{job.id}</strong>
                    <span>
                      TRC-8F2{index}A{8 - index}
                    </span>
                  </td>
                  <td>{job.invoice}</td>
                  <td>
                    <strong>{job.object}</strong>
                  </td>
                  <td>{job.content}</td>
                  <td>
                    <strong>{job.user}</strong>
                    <span>{job.time}</span>
                  </td>
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
                        notify(
                          job.status === "等待审批"
                            ? "已审批并提交 NetSuite 回写队列"
                            : job.status === "失败"
                              ? "失败任务已安全重试"
                              : "已打开完整请求与响应日志",
                        )
                      }
                    >
                      {job.status === "等待审批" ? "审批并提交" : job.status === "失败" ? "重试" : "查看日志"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="audit-footer">
          <span>审计保留：7 年</span>
          <span>最近操作：陈静 · 10:31 · 审批匹配单 MAT-202608-01876</span>
          <span>权限角色：AP 财务经理</span>
        </div>
      </article>
    </>
  );
}
