import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import "./finance-workbench-example.css";

type Tab = "queue" | "source" | "matching" | "followup" | "exceptions";
type Case = "candidate" | "missing" | "changed";

const tabs: { id: Tab; label: string }[] = [
  { id: "queue", label: "财务待办" },
  { id: "source", label: "来源审核" },
  { id: "matching", label: "发票行匹配" },
  { id: "followup", label: "收票跟进" },
  { id: "exceptions", label: "异常与接入" },
];

const sampleLines = [
  { id: "9601", name: "胸章机", quantity: "10 台", amount: "¥913.00" },
  { id: "9604", name: "胸章", quantity: "2000 套", amount: "¥1,560.00" },
];

function Status({ children, tone = "neutral" }: { children: string; tone?: "neutral" | "warn" | "ok" }) {
  return <span className={`fw-example__status fw-example__status--${tone}`}>{children}</span>;
}

function SectionTitle({ title, description }: { title: string; description?: string }) {
  return (
    <div className="fw-example__section-title">
      <h2>{title}</h2>
      {description && <p>{description}</p>}
    </div>
  );
}

export function FinanceWorkbenchExample() {
  const [tab, setTab] = useState<Tab>("queue");
  const [selectedCase, setSelectedCase] = useState<Case>("candidate");
  const [customsClue, setCustomsClue] = useState("CD000252");
  const hasSampleCandidate = ["CD000252", "310120260519278380"].includes(customsClue.trim());

  return (
    <div className="fw-example">
      <nav className="fw-example__tabs" aria-label="闭环示例视图">
        {tabs.map((item) => (
          <button key={item.id} type="button" aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "queue" && (
        <section aria-label="财务待办示例">
          <div className="fw-example__context">
            <strong>从现有财务列表进入</strong>
            <span>
              现有接口提供报关单、关联子采购行、审核状态与允许操作原因；这里展示建议的待办排列方式。
            </span>
            <a href="/finance-reconciliation">打开正式财务核对 →</a>
          </div>
          <div className="fw-example__split fw-example__split--queue">
            <div className="fw-example__panel fw-example__queue">
              <SectionTitle title="待办队列" description="点击样例切换下一步处理方式" />
              <button
                type="button"
                aria-pressed={selectedCase === "candidate"}
                onClick={() => setSelectedCase("candidate")}
              >
                <strong>CD000252 · 逐行候选</strong>
                <span>2 条发票行 · ¥2,473.00</span>
                <Status tone="warn">待主体与占用核实</Status>
              </button>
              <button
                type="button"
                aria-pressed={selectedCase === "missing"}
                onClick={() => setSelectedCase("missing")}
              >
                <strong>缺子采购来源 · 状态示例</strong>
                <span>报关单有记录，关联采购行 0 条</span>
                <Status tone="warn">阻断审核</Status>
              </button>
              <button
                type="button"
                aria-pressed={selectedCase === "changed"}
                onClick={() => setSelectedCase("changed")}
              >
                <strong>CD000870 · 变化示例</strong>
                <span>原审核依据与新来源不同</span>
                <Status tone="warn">需重新审核</Status>
              </button>
            </div>
            <div className="fw-example__panel">
              {selectedCase === "candidate" && (
                <>
                  <SectionTitle
                    title="CD000252 · 发票匹配候选"
                    description="采购与发票行核对一致，尚未确认分配"
                  />
                  <div className="fw-example__facts">
                    <div>
                      <span>母采购单</span>
                      <strong>YE-ST251231-Y593</strong>
                    </div>
                    <div>
                      <span>子采购单</span>
                      <strong>YE-ST251231-Y593-1</strong>
                    </div>
                    <div>
                      <span>真实报关号码</span>
                      <strong>310120260519278380</strong>
                    </div>
                  </div>
                  <div className="fw-example__table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>发票行</th>
                          <th>子采购报关行</th>
                          <th>报关数量/单位</th>
                          <th className="fw-example__number">采购含税额</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sampleLines.map((line) => (
                          <tr key={line.id}>
                            <td>{line.name}</td>
                            <td>
                              {line.id} · {line.name}
                            </td>
                            <td>{line.quantity}</td>
                            <td className="fw-example__number">{line.amount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="fw-example__warning">
                    销售方“义乌市尚图数码影像有限公司”与子单供应商“浙江义乌市尚图数码影像有限公司”名称不同。保存前须核税号与主体映射，并检查行占用。
                  </p>
                  <Button onClick={() => setTab("matching")}>查看匹配示例</Button>
                </>
              )}
              {selectedCase === "missing" && (
                <>
                  <SectionTitle
                    title="来源缺失，暂不能审核"
                    description="“0 条子采购行”应直接转成待办，而非只留下禁用按钮"
                  />
                  <p className="fw-example__body">
                    核实 NS
                    同步批次、子单来源引用和报关行关联；补齐后重新生成待审快照。同步完成时间应由实际批次返回，本示例不填写虚构时间。
                  </p>
                  <a className="ui-button ui-button--secondary" href="/sync/ns">
                    前往 NS 数据同步
                  </a>
                </>
              )}
              {selectedCase === "changed" && (
                <>
                  <SectionTitle
                    title="来源变化，等待重审"
                    description="旧审核记录和已确认分配仍需保留可追溯历史"
                  />
                  <p className="fw-example__body">
                    逐行展示新旧数量、单位、金额和子单关联差异。完成重审前，不再用旧获批范围产生新的分配。
                  </p>
                  <Button onClick={() => setTab("source")}>查看审核范围示例</Button>
                </>
              )}
            </div>
          </div>
        </section>
      )}

      {tab === "source" && (
        <section aria-label="来源审核示例">
          <div className="fw-example__context">
            <strong>沿用当前报关整单审核</strong>
            <span>
              正式页已有三级展开和不可变快照；本视图演示如何把摘要、逐行依据与后续获批范围放在同一屏。
            </span>
            <a href="/finance-reconciliation">查看现有审核页 →</a>
          </div>
          <SectionTitle
            title="CD000252 · 报关与子采购对照"
            description="母单 YE-ST251231-Y593 · 子单 YE-ST251231-Y593-1 · 报关号码 310120260519278380"
          />
          <div className="fw-example__summary">
            <span>2 条报关行</span>
            <span>2 条子采购行</span>
            <span>采购含税合计 ¥2,473.00</span>
            <Status tone="warn">主体差异待核实</Status>
          </div>
          <div className="fw-example__split">
            <div className="fw-example__panel">
              <h3>报关行 · NS 来源</h3>
              <p className="fw-example__muted">报关美元金额是独立证据，不与人民币发票直接比较。</p>
              {sampleLines.map((line, index) => (
                <div className="fw-example__row" key={line.id}>
                  <div>
                    <strong>
                      第 {index + 1} 行 · {line.name}
                    </strong>
                    <span>报关数量 {line.quantity}</span>
                  </div>
                  <Status tone="ok">已找到子单行</Status>
                </div>
              ))}
            </div>
            <div className="fw-example__panel">
              <h3>子采购报关明细 · NS 来源</h3>
              <p className="fw-example__muted">匹配单位取子单的报关单位；原始单位为空时不回退母单。</p>
              {sampleLines.map((line) => (
                <div className="fw-example__row" key={line.id}>
                  <div>
                    <strong>
                      {line.id} · {line.name}
                    </strong>
                    <span>
                      报关 {line.quantity} · 含税 {line.amount}
                    </span>
                  </div>
                  <Status tone="ok">逐行对应</Status>
                </div>
              ))}
            </div>
          </div>
          <div className="fw-example__scope">
            <div>
              <h3>目标：保存本次获批范围和版本</h3>
              <p>
                审核后形成每条子采购行可供匹配的数量、币种、含税金额与版本标识。当前正式审核尚未向匹配提供这一约束。
              </p>
            </div>
            <Status>待实现</Status>
          </div>
          <details className="fw-example__details">
            <summary>查看确认前应展示的差异摘要</summary>
            <p>
              2 条报关行对应 2 条采购明细；主体名称差异 1
              项。长确认窗先显示摘要，再按报关行展开原值。审核人、时间、备注和来源批次进入操作记录。
            </p>
          </details>
        </section>
      )}

      {tab === "matching" && (
        <section aria-label="发票匹配示例">
          <div className="fw-example__context">
            <strong>接到当前发票行匹配</strong>
            <span>现有匹配页已有候选、人工复核和占用保护；目标是在确认前增加获批版本与剩余额度校验。</span>
            <a href="/invoices">从进项发票选择真实发票 →</a>
          </div>
          <div className="fw-example__split">
            <div className="fw-example__panel">
              <SectionTitle
                title="备注可缺母单"
                description="输入 CD 编号或真实报关号，定位关联的子采购候选"
              />
              <label className="fw-example__label" htmlFor="fw-customs-clue">
                报关线索
                <input
                  id="fw-customs-clue"
                  value={customsClue}
                  onChange={(event) => setCustomsClue(event.target.value)}
                  placeholder="CD 编号或真实报关号码"
                />
              </label>
              <p className="fw-example__muted" role="status">
                {hasSampleCandidate
                  ? "示例候选：YE-ST251231-Y593-1。候选不等于已确认分配。"
                  : "此交互仅内置 CD000252 样例；正式查询由现有匹配接口与 NS 来源提供。"}
              </p>
            </div>
            <div className="fw-example__panel">
              <SectionTitle title="保存前核验" description="以下状态是目标流程，并非已接通的后端结论" />
              <div className="fw-example__row">
                <div>
                  <strong>销售方与子单供应商</strong>
                  <span>核对税号与已确认主体映射</span>
                </div>
                <Status tone="warn">待核实</Status>
              </div>
              <div className="fw-example__row">
                <div>
                  <strong>审核获批版本和剩余额度</strong>
                  <span>逐行校验数量与人民币含税金额</span>
                </div>
                <Status>待实现</Status>
              </div>
              <div className="fw-example__row">
                <div>
                  <strong>行占用与重复分配</strong>
                  <span>以现有匹配服务的占用保护为基础</span>
                </div>
                <Status tone="warn">保存前检查</Status>
              </div>
            </div>
          </div>
          {hasSampleCandidate && (
            <div className="fw-example__panel fw-example__panel--spaced">
              <SectionTitle
                title="发票行 → 子采购报关行"
                description="按品名、数量、子采购报关单位和采购人民币含税额逐行核对"
              />
              <div className="fw-example__table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>发票行</th>
                      <th>候选子采购行</th>
                      <th>数量/单位</th>
                      <th className="fw-example__number">含税额</th>
                      <th>判断</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sampleLines.map((line) => (
                      <tr key={line.id}>
                        <td>{line.name}</td>
                        <td>
                          {line.id} · {line.name}
                        </td>
                        <td>
                          {line.quantity} ↔ {line.quantity}
                        </td>
                        <td className="fw-example__number">
                          {line.amount} ↔ {line.amount}
                        </td>
                        <td>逐行一致</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="fw-example__warning">
                该样例可列为高可信候选。主体与审核额度尚未核实，不能在此确认分配；本页不会调用保存接口。
              </p>
            </div>
          )}
          <div className="fw-example__panel fw-example__panel--spaced">
            <h3>发票查验与票面状态 · 待新增</h3>
            <p className="fw-example__body">
              保存查验结果、时间、作废及红冲关系。业务匹配成功不替代票面查验。
            </p>
          </div>
        </section>
      )}

      {tab === "followup" && (
        <section aria-label="收票跟进示例">
          <div className="fw-example__context">
            <strong>沿用已生成的开票任务</strong>
            <span>当前任务已有审核版本、合同与人工通知节点；“部分收票/已收齐”仍未由已匹配发票驱动。</span>
            <a href="/invoice-followup">打开正式开票跟进 →</a>
          </div>
          <SectionTitle
            title="任务与收票状态"
            description="下表是目标状态示例；已确认且有效的发票行才计入收票"
          />
          <div className="fw-example__panel">
            <div className="fw-example__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>审核范围</th>
                    <th>已确认发票分配</th>
                    <th>剩余</th>
                    <th>目标状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      CD000252<small>假设完成审核后的示意</small>
                    </td>
                    <td>¥2,473.00</td>
                    <td>
                      ¥0.00<small>两条目前仅为候选</small>
                    </td>
                    <td>¥2,473.00</td>
                    <td>
                      <Status tone="warn">未收票</Status>
                    </td>
                  </tr>
                  <tr>
                    <td>其他任务 · 示例</td>
                    <td>¥8,000.00</td>
                    <td>¥3,000.00</td>
                    <td>¥5,000.00</td>
                    <td>
                      <Status tone="warn">部分收票</Status>
                    </td>
                  </tr>
                  <tr>
                    <td>其他任务 · 示例</td>
                    <td>¥5,200.00</td>
                    <td>¥5,200.00</td>
                    <td>¥0.00</td>
                    <td>
                      <Status tone="ok">已收齐</Status>
                    </td>
                  </tr>
                  <tr>
                    <td>CD000870 · 变化示意</td>
                    <td>待重审</td>
                    <td>保留历史</td>
                    <td>待重算</td>
                    <td>
                      <Status>待复核</Status>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="fw-example__scope">
            <div>
              <h3>目标：按确认分配回连任务</h3>
              <p>
                来源审核版本 → 获批行额度 → 开票任务 → 发票行 →
                子采购行。支持按供应商、期间及报关单追溯余额和操作记录。
              </p>
            </div>
            <Status>待实现</Status>
          </div>
        </section>
      )}

      {tab === "exceptions" && (
        <section aria-label="异常与接入示例">
          <SectionTitle
            title="异常工作台"
            description="缺来源、主体不一致、单位/币种缺失、多候选、超额、红冲和来源变化都要有责任角色与处理结果"
          />
          <div className="fw-example__panel">
            <div className="fw-example__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>异常</th>
                    <th>影响</th>
                    <th>责任角色</th>
                    <th>下一步</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>缺子采购来源</td>
                    <td>无法审核</td>
                    <td>来源维护</td>
                    <td>核实 NS 同步及行关联</td>
                  </tr>
                  <tr>
                    <td>供应商主体名称差异</td>
                    <td>无法自动确认匹配</td>
                    <td>财务审核</td>
                    <td>核税号并维护主体档案</td>
                  </tr>
                  <tr>
                    <td>来源版本变化</td>
                    <td>暂停旧范围新增分配</td>
                    <td>财务复核</td>
                    <td>查看差异并重审</td>
                  </tr>
                  <tr>
                    <td>超额、红冲或多候选</td>
                    <td>进入人工复核</td>
                    <td>差异确认</td>
                    <td>记录证据与处理结论</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div className="fw-example__split fw-example__split--spaced">
            <div className="fw-example__panel">
              <h3>NS 来源 · 已有手动同步</h3>
              <p className="fw-example__body">
                现有同步页可分页拉取并保存报关与子采购来源。目标增加持久批次、失败恢复、来源版本与完整性监控。
              </p>
              <a href="/sync/ns">查看现有 NS 同步 →</a>
            </div>
            <div className="fw-example__panel">
              <h3>柠檬云发票 · 当前 Excel 导入</h3>
              <p className="fw-example__body">
                当前仅覆盖“采购固定资产”。API
                接入前需确认产品线、账套权限及商品明细字段，再实现增量同步、去重、票面变更。
              </p>
              <a href="/sync/lemon">查看现有发票导入 →</a>
            </div>
          </div>
          <div className="fw-example__split fw-example__split--spaced">
            <div className="fw-example__panel">
              <h3>主体档案与多人权限 · 待新增</h3>
              <p className="fw-example__body">
                维护法定名称、曾用名、税号、核实证据；区分来源维护、财务审核、差异确认和回写权限。
              </p>
            </div>
            <div className="fw-example__panel">
              <h3>对账与审计 · 待新增</h3>
              <p className="fw-example__body">
                按供应商、期间、报关单追溯审核版本、任务、发票行、子采购行、剩余额度及操作人。
              </p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
