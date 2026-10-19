import { Link } from "react-router";
import { Button } from "../../shared/components/Button";
import { paths } from "../../app/paths";
import type { useLemonInvoices } from "./useLemonInvoices";
import { LemonBusinessTypes } from "./LemonBusinessTypes";

type Props = ReturnType<typeof useLemonInvoices>;
export function LemonInvoiceView({
  data,
  accounts,
  asid,
  setAsid,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  businessTypes,
  setBusinessTypes,
  busy,
  error,
  run,
}: Props) {
  const latest = data?.latest;
  return (
    <section
      className="lemon-invoices"
      id="lemon-api-import"
      aria-labelledby="lemon-invoices-title"
      aria-busy={Boolean(busy)}
    >
      <header className="lemon-invoices__heading">
        <div>
          <h2 id="lemon-invoices-title">从柠檬云拉取进项发票</h2>
          <p>选择已授权账套，按开票日期读取进项发票，并保存勾选的业务类型。</p>
        </div>
        <Button disabled={Boolean(busy)} onClick={() => void run("refresh")}>
          刷新同步状态
        </Button>
      </header>
      {error && (
        <p role="alert" className="lemon-invoices__error">
          {error}。请求中断时请先刷新查询原结果。
        </p>
      )}
      {!data && !error && <p role="status">正在读取同步配置…</p>}
      {data && (
        <>
          <div className="lemon-invoices__account">
            <p>
              当前账套：
              <strong>{data.selected ? `${data.selected.name}（${data.selected.asid}）` : "尚未选择"}</strong>
            </p>
            <Button disabled={Boolean(busy) || !data.query.allowed} onClick={() => void run("query")}>
              {busy === "query" ? "正在查询账套…" : "查询授权账套"}
            </Button>
          </div>
          {!data.query.allowed && <p>{data.query.reason}</p>}
          {accounts?.length === 0 && (
            <p role="status">当前账号没有返回可用账套，请核实账套版本与应用访问权限。</p>
          )}
          {accounts && accounts.length > 0 && (
            <form
              className="lemon-invoices__selection"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void run("select");
              }}
            >
              <label htmlFor="lemon-asid">
                授权账套
                <select
                  id="lemon-asid"
                  value={asid}
                  disabled={Boolean(busy)}
                  onChange={(event) => setAsid(event.target.value)}
                >
                  <option value="">请选择账套</option>
                  {accounts.map((account) => (
                    <option key={account.asid} value={account.asid}>
                      {account.name}（{account.asid}）
                    </option>
                  ))}
                </select>
              </label>
              <Button type="submit" disabled={Boolean(busy) || !data.query.allowed}>
                {busy === "select" ? "正在核实账套…" : "使用此账套"}
              </Button>
            </form>
          )}
          <form
            noValidate
            className="lemon-invoices__form"
            onSubmit={(event) => {
              event.preventDefault();
              void run("pull");
            }}
          >
            <LemonBusinessTypes
              options={data.businessTypeOptions}
              selected={businessTypes}
              onChange={setBusinessTypes}
              disabled={Boolean(busy)}
            />
            <label htmlFor="lemon-start">
              起始开票日期
              <input
                id="lemon-start"
                type="date"
                value={startDate}
                disabled={Boolean(busy)}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label htmlFor="lemon-end">
              结束开票日期
              <input
                id="lemon-end"
                type="date"
                value={endDate}
                disabled={Boolean(busy)}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
            <Button type="submit" variant="primary" disabled={Boolean(busy) || !data.sync.allowed}>
              {busy === "pull" ? "正在拉取并保存…" : "拉取并保存"}
            </Button>
          </form>
          <p>{data.sync.reason}。单次最多 366 天、2000 张；超限时缩小日期范围。</p>
          <p className="lemon-invoices__note">
            专业版拉取时同步读取商品明细；明细完整后按已审核子采购行生成建议，须人工确认。
            专业版已入库票头可按原日期范围重新拉取补齐。默认版暂只读取票头；定时同步与附件同步尚未接入。
          </p>
          {latest && (
            <div className="lemon-invoices__result" role="status">
              <h3>最近一次同步</h3>
              <p>
                {latest.accountName}（{latest.asid}） · {latest.startDate} 至 {latest.endDate}
              </p>
              <p>本次业务类型：{latest.businessTypes.join("、")}</p>
              {latest.status === "running" && (
                <p>执行中或结果待核实。请刷新同步状态；若服务曾重启，请管理员核实此请求，不能直接重发。</p>
              )}
              {latest.status === "failed" && (
                <p className="lemon-invoices__error">本次未保存：{latest.error}</p>
              )}
              {latest.status === "completed" && latest.result && (
                <>
                  <p>{latest.result.message}</p>
                  <dl>
                    {[
                      ["读取", latest.result.fetched],
                      ["未选类型跳过", latest.result.excluded],
                      ["新增", latest.result.created],
                      ["更新版本", latest.result.updated],
                      ["重复跳过", latest.result.unchanged],
                      ["明细完整", latest.result.completeDetails ?? "—"],
                      ["明细待补齐或待核实", latest.result.pendingDetails],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value} 张</dd>
                      </div>
                    ))}
                  </dl>
                  {Boolean(latest.result.detailIssues?.length) && (
                    <details>
                      <summary>
                        查看未补齐原因（{latest.result.detailIssueCount} 张，最多展示 100 张）
                      </summary>
                      <ul>
                        {latest.result.detailIssues?.map((issue) => (
                          <li key={issue.number}>
                            {issue.number}：{issue.reason}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              )}
              <p className="lemon-invoices__request">请求编号：{latest.requestId}</p>
              <Link to={paths.invoices}>查看发票台账</Link>
              {" · "}
              <Link to={paths.matching}>审核匹配建议</Link>
            </div>
          )}
        </>
      )}
    </section>
  );
}
