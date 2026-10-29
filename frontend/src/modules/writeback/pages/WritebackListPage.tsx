import { Link } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import {
  Button,
  Card,
  CardHeader,
  CardFooter,
  DataTable,
  EmptyState,
  ErrorState,
  Pagination,
  Skeleton,
  Segmented,
} from "../../../shared/components/ui";
import { ParentOrderNumbers } from "../components/ParentOrderNumbers";
import { WritebackSearch } from "../components/WritebackSearch";
import { WritebackStats, groupLabels } from "../components/WritebackStats";
import { WritebackStateBadge } from "../components/WritebackStateBadge";
import { useWritebackList } from "../hooks/useWritebackList";
import type { WritebackGroup } from "../types";
import "../writeback.css";

export function WritebackListPage() {
  const { query, data, error, loading, change, reload, selected } = useWritebackList();
  function select(group: WritebackGroup | "") {
    change({ group, state: "", page: 1 });
  }
  const reset = () =>
    change({
      keyword: "",
      taskNo: "",
      invoiceNo: "",
      supplierName: "",
      parentOrderNo: "",
      group: "",
      state: "",
      page: 1,
    });
  const filtered = Boolean(
    query.keyword ||
      query.taskNo ||
      query.invoiceNo ||
      query.supplierName ||
      query.parentOrderNo ||
      query.group ||
      query.state,
  );
  return (
    <div className="wb-prepare">
      {data?.counts ? (
        <WritebackStats counts={data.counts} selected={selected} onSelect={select} />
      ) : loading ? (
        <Skeleton rows={1} label="正在读取回写概况" />
      ) : null}
      <Card className="wb-task-list">
        <CardHeader
          title="回写任务"
          description="概况按当前查询条件统计，不受状态和分页影响；历史扫描任务须人工核实。"
          actions={
            <>
              <Segmented<keyof typeof groupLabels>
                label="按回写状态筛选"
                value={selected}
                disabled={loading}
                options={(Object.keys(groupLabels) as (keyof typeof groupLabels)[]).map((key) => ({
                  value: key,
                  label: groupLabels[key],
                  count: data?.counts?.[key],
                }))}
                onChange={(value) => select(value === "all" ? "" : value)}
              />
              <Button disabled={loading} onClick={reload}>
                刷新列表
              </Button>
            </>
          }
        />
        <WritebackSearch
          query={query}
          states={data?.states}
          busy={loading}
          onSearch={change}
          onReset={reset}
        />
        {loading ? (
          <Skeleton label="正在加载回写任务" />
        ) : error ? (
          <ErrorState
            title="任务加载失败"
            message={error}
            action={<Button onClick={reload}>重新加载</Button>}
          />
        ) : data?.items.length ? (
          <DataTable
            label="回写任务"
            rows={data.items}
            rowKey={(row) => row.id}
            minWidth={1050}
            columns={[
              {
                key: "invoice",
                header: "发票 / 任务",
                render: (row) => (
                  <>
                    <Link to={writebackRequestPath(row.id)}>{row.invoiceNo}</Link>
                    <small className="wb-secondary">{row.taskNo}</small>
                  </>
                ),
              },
              { key: "parent", header: "母采购单", render: (row) => <ParentOrderNumbers task={row} /> },
              { key: "vendor", header: "供应商", render: (row) => row.vendorName },
              { key: "amount", header: "含税金额（元）", align: "right", render: (row) => row.amount },
              { key: "state", header: "状态", render: (row) => <WritebackStateBadge task={row} /> },
              { key: "reason", header: "处理说明", render: (row) => row.reason },
            ]}
          />
        ) : (
          <EmptyState
            title={filtered ? "没有符合条件的回写任务" : "暂无回写任务"}
            description={
              filtered
                ? "可调整状态或搜索条件，也可清空条件查看全部任务。"
                : "完成整票分配审核后自动生成任务；历史发票可在匹配详情重新检查。"
            }
            action={filtered ? <Button onClick={reset}>查看全部任务</Button> : undefined}
          />
        )}
        {data && !loading && !error && (
          <CardFooter>
            <Pagination
              label="回写任务分页"
              total={data.total}
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20, 50, 100]}
              disabled={loading}
              onPageChange={(page) => change({ page })}
              onPageSizeChange={(pageSize) => change({ pageSize, page: 1 })}
            />
          </CardFooter>
        )}
      </Card>
      <details className="wb-state-help">
        <summary>回写状态与规则</summary>
        <p>
          待回写：待匹配账单、等待账单、待确认账单、待确认回写预览、待写入
          NS。确认方案和必要的预览后，写入开关与供应商白名单均满足才可写入。
        </p>
        <p>回写中：正在写入 NS，请勿重复提交。NS 已登记：NS 已完整登记，或经人工核实已完整登记。</p>
        <p>
          需处理：待处理、NS
          已有同号登记、部分写入及结果不明。部分写入或结果不明须先人工核实，没有直接重发入口。
        </p>
        <p>审核已失效：未写入任务的审核依据已变化，需重新核对；保留原任务供追溯。</p>
      </details>
    </div>
  );
}
