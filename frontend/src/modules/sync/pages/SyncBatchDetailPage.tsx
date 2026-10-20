import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { paths, syncBatchPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { SyncBatchAccounts } from "../components/SyncBatchAccounts";
import { SyncPhaseTag } from "../components/SyncPhaseTag";
import { useSyncBatchDetail } from "../hooks/useSyncBatchDetail";
import { syncTime } from "../types/background";
import "../components/sync-background.css";
import "../components/sync-layout.css";

export function SyncBatchDetailPage() {
  const { requestId = "" } = useParams();
  const [query, setQuery] = useSearchParams();
  const { data, error, busy, refresh, retry } = useSyncBatchDetail(
    requestId,
    Number(query.get("page") || "1"),
  );
  const navigate = useNavigate();
  if (!data)
    return (
      <section className="sync-background" aria-label="后台任务详情">
        {error ? (
          <>
            <p role="alert" className="sync-background__error">
              {error}
            </p>
            <Button onClick={refresh}>刷新任务状态</Button>
          </>
        ) : (
          <p role="status">正在读取任务详情…</p>
        )}
      </section>
    );
  const facts = [
    ["开票日期范围", `${data.startDate} 至 ${data.endDate}`],
    ["业务类型", data.businessTypes.join("、")],
    ["触发方式", data.trigger === "schedule" ? "定时计划" : "手动提交"],
    ["提交时间", syncTime(data.createdAt)],
    ["结束时间", syncTime(data.finishedAt)],
  ];
  const totals = [
    ["读取", data.fetched],
    ["新增", data.created],
    ["更新", data.updated],
    ["失败", data.failed],
  ] as const;
  return (
    <div className="sync-background__stack">
      <section className="sync-background sync-background--flush" aria-label="批次概况">
        <div className="sync-background__head">
          <div className="sync-background__inline">
            <SyncPhaseTag phase={data.phase} label={data.label} />
            <h2>{data.message}</h2>
          </div>
          <div className="sync-background__inline">
            <Button onClick={refresh}>刷新任务状态</Button>
            <Button
              variant="primary"
              disabled={busy || !data.retry.allowed}
              onClick={() => void retry((id) => navigate(syncBatchPath(id)))}
            >
              {busy ? "正在提交…" : "重试失败分片"}
            </Button>
          </div>
        </div>
        {error && (
          <p role="alert" className="sync-background__error sync-background__body">
            {error}
          </p>
        )}
        {!data.retry.allowed && <p className="sync-background__body sync-muted">{data.retry.reason}</p>}
        <dl className="sync-facts">
          {facts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <dl className="sync-facts sync-facts--totals">
          {totals.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {data.phase === "unknown" && (
          <p role="alert" className="sync-background__error sync-background__body">
            部分提交结果无法确认，已保留原请求。请管理员核实进程与数据库提交状态，不能直接重发或清除运行记录。
          </p>
        )}
      </section>
      <section className="sync-background sync-background--flush" aria-label="各账套执行结果">
        <div className="sync-background__head">
          <h2>各账套执行结果（{data.total}）</h2>
          <Link to={paths.invoices}>查看发票台账 →</Link>
        </div>
        <div className="sync-background__body">
          {data.accounts.length === 0 ? (
            <p role="status">
              {data.poll
                ? "正在等待后台发现账套，稍后自动更新。"
                : "本批次没有生成账套任务，请查看上方原因。"}
            </p>
          ) : (
            <SyncBatchAccounts accounts={data.accounts} />
          )}
          {data.total > 0 && (
            <Pagination
              label="账套结果分页"
              total={data.total}
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20]}
              onPageChange={(page) => setQuery({ page: String(page) })}
              onPageSizeChange={() => {}}
            />
          )}
          <p className="sync-muted">
            无新增属于正常结果；明细待补齐可在进项发票中补拉。批次编号：{data.requestId}
          </p>
        </div>
      </section>
    </div>
  );
}
