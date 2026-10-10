import { Link } from "react-router";
import { paths } from "../../app/paths";

/** 保留同步中心原有布局，平台卡片作为独立同步页入口。 */
export function SyncOverview() {
  return (
    <>
      <div className="sync-overview__cards" id="sync-platforms">
        <Link className="sync-overview__card" to={paths.syncNs} aria-label="NetSuite，进入 NS 数据同步">
          <div className="sync-overview__card-head">
            <span className="sync-overview__logo">N</span>
            <div>
              <h2>NetSuite</h2>
              <small>OAuth 2.0 M2M · SuiteTalk REST</small>
            </div>
            <span className="sync-overview__badge">按需拉取</span>
          </div>
          <dl>
            <div>
              <dt>最后成功</dt>
              <dd>暂无同步记录</dd>
            </div>
            <div>
              <dt>同步游标</dt>
              <dd>尚未启用</dd>
            </div>
            <div>
              <dt>今日记录</dt>
              <dd>暂无统计</dd>
            </div>
            <div>
              <dt>失败任务</dt>
              <dd>暂无统计</dd>
            </div>
          </dl>
          <span className="sync-overview__enter">进入 NS 数据同步 →</span>
        </Link>
        <Link
          className="sync-overview__card"
          to={paths.syncLemon}
          aria-label="柠檬云发票，进入柠檬云数据同步"
        >
          <div className="sync-overview__card-head">
            <span className="sync-overview__logo sync-overview__logo--lemon">柠</span>
            <div>
              <h2>柠檬云发票</h2>
              <small>Excel 发票导入 · API 待接入</small>
            </div>
            <span className="sync-overview__badge">文件导入</span>
          </div>
          <dl>
            <div>
              <dt>最后成功</dt>
              <dd>暂无同步记录</dd>
            </div>
            <div>
              <dt>同步游标</dt>
              <dd>尚未启用</dd>
            </div>
            <div>
              <dt>今日发票</dt>
              <dd>暂无统计</dd>
            </div>
            <div>
              <dt>失败任务</dt>
              <dd>暂无统计</dd>
            </div>
          </dl>
          <span className="sync-overview__enter">进入柠檬云数据同步 →</span>
        </Link>
        <article className="sync-overview__card">
          <div className="sync-overview__card-head">
            <span className="sync-overview__logo sync-overview__logo--pipeline">⇄</span>
            <div>
              <h2>对账数据管道</h2>
              <small>标准化 → 匹配 → 异常 → 回写</small>
            </div>
            <span className="sync-overview__badge">待接入</span>
          </div>
          <div className="sync-overview__steps">
            <b>拉取</b>
            <span>→</span>
            <b>清洗</b>
            <span>→</span>
            <b>匹配</b>
            <span>→</span>
            <b>审批</b>
            <span>→</span>
            <b>回写</b>
          </div>
          <p>自动调度与批次重算尚未接入。</p>
          <button className="sync-overview__enter" disabled>
            重算最近批次
          </button>
        </article>
      </div>
      <section className="sync-overview__tasks">
        <div className="sync-page__heading">
          <div>
            <h2>同步任务记录</h2>
            <p>所有时间为 Asia/Shanghai · 任务历史尚未接入</p>
          </div>
          <button className="ui-button ui-button--secondary" disabled>
            导出日志
          </button>
        </div>
        <div className="sync-page__table">
          <table>
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
              <tr>
                <td colSpan={7} className="sync-overview__empty">
                  暂无可展示的同步任务记录，请点击上方平台卡片进入对应同步页面。
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
