import { Link, useParams } from "react-router";
import { paths } from "../../../app/paths";
import {
  Alert,
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { useNsPlanBatch } from "../hooks/useNsPlanBatch";
import { syncTime } from "../types/background";
import { statusTone, type NsBatchPage } from "../types/ns-plan";
import "../components/sync-background.css";
import "../components/sync-layout.css";

function pageNote(row: NsBatchPage) {
  if (row.progress) {
    const step = row.progress.total === null ? "" : ` ${row.progress.completed ?? 0}/${row.progress.total}`;
    return `${row.progress.label}${step} · 已用 ${row.progress.elapsedSeconds} 秒`;
  }
  return row.error ?? "";
}

const columns: Column<NsBatchPage>[] = [
  { key: "index", header: "分页", width: "72px", render: (row) => `第 ${row.index} 页` },
  {
    key: "status",
    header: "状态",
    width: "110px",
    render: (row) => <Badge tone={statusTone(row.status)}>{row.statusLabel}</Badge>,
  },
  { key: "count", header: "本页单据", align: "right", width: "84px", render: (row) => row.count ?? "—" },
  { key: "saved", header: "已保存", align: "right", width: "72px", render: (row) => row.saved },
  { key: "skipped", header: "未出库跳过", align: "right", width: "96px", render: (row) => row.skipped },
  { key: "failed", header: "失败", align: "right", width: "64px", render: (row) => row.failed },
  {
    key: "note",
    header: "进度与原因",
    render: (row) => (
      <>
        {pageNote(row)}
        {row.failures.length > 0 && (
          <ul className="sync-background__windows">
            {row.failures.map((item) => (
              <li key={item.id}>
                <strong>{item.number}</strong>：{item.reason}
              </li>
            ))}
          </ul>
        )}
        <small>请求编号 {row.requestId}</small>
      </>
    ),
  },
];

/** NS 计划批次详情：按分页展示真实执行状态、执行中阶段进度和失败单据原因。 */
export function NsPlanBatchPage() {
  const { requestId = "" } = useParams();
  const { data, error, refresh } = useNsPlanBatch(requestId);
  if (!data)
    return (
      <section className="sync-background" aria-label="NS 计划批次详情">
        {error ? (
          <ErrorState
            title="批次读取失败"
            message={error}
            action={<Button onClick={refresh}>重新读取</Button>}
          />
        ) : (
          <Skeleton label="正在读取批次详情" />
        )}
      </section>
    );
  const facts = [
    ["单据类型", data.kindLabel],
    ["创建日期范围", `${data.startDate} 至 ${data.endDate}`],
    ["触发方式", data.trigger === "schedule" ? "定时计划" : "手动提交"],
    ["触发时间", syncTime(data.createdAt)],
    ["结束时间", syncTime(data.finishedAt)],
  ];
  const totals = [
    ["读取", data.fetched],
    ["新增", data.created],
    ["更新", data.updated],
    ["失败单据", data.failed],
  ] as const;
  return (
    <div className="sync-background__stack">
      <section className="sync-background sync-background--flush" aria-label="批次概况">
        <div className="sync-background__head">
          <div className="sync-background__inline">
            <Badge tone={statusTone(data.phase)}>{data.label}</Badge>
            <h2>{data.message}</h2>
          </div>
          <Button onClick={refresh}>刷新批次状态</Button>
        </div>
        {error && (
          <div className="sync-background__body">
            <Alert tone="danger">{error}；以下为上次读取的结果。</Alert>
          </div>
        )}
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
          <div className="sync-background__body">
            <Alert tone="warning" title="结果待核实">
              有分页的保存结果无法确认，后续分页已停止且不会自动重试，定时计划已自动暂停。请先在
              <Link to={paths.review}>财务核对</Link>
              核对本地已保存单据，再到 NS 数据同步页重新启用计划。
            </Alert>
          </div>
        )}
      </section>
      <section className="sync-background sync-background--flush" aria-label="分页执行结果">
        <div className="sync-background__head">
          <h2>分页执行结果（{data.pages.length}）</h2>
          <Link to={paths.syncNs}>返回 NS 数据同步 →</Link>
        </div>
        <div className="sync-background__body">
          {data.pages.length === 0 ? (
            <EmptyState
              title={data.poll ? "等待后台执行第一页" : "本批次没有执行任何分页"}
              description={data.poll ? "后台每隔数秒推进一次，页面会自动更新。" : "请查看上方原因。"}
            />
          ) : (
            <DataTable
              label="NS 计划分页结果表"
              columns={columns}
              rows={data.pages}
              rowKey={(row) => row.requestId}
              minWidth={860}
            />
          )}
          <p className="sync-muted">
            每页最多 20 张入口单据，按完整报关关联组分别保存；同一页未写入时间隔 1
            分钟后按原游标重新排队。批次编号：
            {data.requestId}
          </p>
        </div>
      </section>
    </div>
  );
}
