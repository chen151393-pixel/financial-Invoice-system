import { useState } from "react";
import {
  Alert,
  Badge,
  BatchUpload,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
  Dialog,
  DonutChart,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Gauge,
  Icon,
  MetricCard,
  MetricGrid,
  Pagination,
  Progress,
  SectionTitle,
  Segmented,
  Skeleton,
  StageTabs,
  Stepper,
  TrendChart,
} from "..";
import "./ui-kit.css";

// 以下全部为演示数据，只用于展示组件效果，不来自接口，也不代表任何真实业务。
const DAYS = [
  "10-13",
  "10-14",
  "10-15",
  "10-16",
  "10-17",
  "10-18",
  "10-19",
  "10-20",
  "10-21",
  "10-22",
  "10-23",
  "10-24",
];
const MANUAL = [12, 18, 15, 22, 19, 24, 28, 26, 31, 29, 34, 38];
const LEMON = [20, 22, 25, 24, 30, 28, 33, 35, 34, 39, 41, 44];
const EXCEL = [6, 8, 7, 9, 8, 10, 9, 12, 11, 13, 12, 14];
const TOTAL = MANUAL.map((value, i) => value + LEMON[i] + EXCEL[i]);
const wan = (values: number[]) => values.map((value) => `${value}.00 万`);

const ROWS = [
  {
    id: "1",
    supplier: "深圳第二供应商有限公司",
    record: "CD10086",
    amount: "48,200.00",
    progress: "62.5",
    stage: "部分收票",
    tone: "progress" as const,
  },
  {
    id: "2",
    supplier: "东莞第三供应商有限公司",
    record: "CD10072",
    amount: "12,980.50",
    progress: "0",
    stage: "待通知供应商",
    tone: "warning" as const,
  },
  {
    id: "3",
    supplier: "宁波第四五金制品厂",
    record: "CD10051",
    amount: "0.00",
    progress: "100",
    stage: "开票完成",
    tone: "success" as const,
  },
  {
    id: "4",
    supplier: "苏州第五精密电子有限公司",
    record: "CD10040",
    amount: "7,450.00",
    progress: "0",
    stage: "待供应商开票",
    tone: "info" as const,
  },
];

const STEPS = [
  { key: "review", label: "财务审核", description: "审核已通过", state: "done" as const },
  { key: "documents", label: "资料准备", description: "原件已备齐", state: "done" as const },
  { key: "notification", label: "通知供应商", description: "人工登记已发送", state: "done" as const },
  { key: "invoices", label: "等待收票", description: "已收到发票", state: "done" as const },
  { key: "comparison", label: "发票比对", description: "收票后在发票比对页审核", state: "current" as const },
  { key: "completion", label: "完成", description: "尚缺：回签合同", state: "waiting" as const },
];

// 演示上传：不提交文件，按文件名是否含“8 位以上数字”返回示例结果
async function demoUpload(files: { file: File; target: string }[]) {
  return files.map(({ file, target }) => {
    const number = target || /\d{8,}/.exec(file.name)?.[0] || "";
    return number
      ? {
          filename: file.name,
          target: number,
          status: "saved",
          reason: "演示：已保存",
          paths: [`演示/2026年10月/CD10086_REAL10086/文件_${number}.pdf`],
        }
      : { filename: file.name, target: "", status: "unmatched", reason: "演示：未识别编号", paths: [] };
  });
}

export function UiKitShowcase() {
  const [range, setRange] = useState<"7" | "30">("7");
  const [dialog, setDialog] = useState<"" | "dialog" | "upload">("");
  const [node, setNode] = useState("all");
  const [stage, setStage] = useState("");
  return (
    <div className="uk">
      <Alert tone="info" title="演示数据">
        本页展示统一组件库（shared/components/ui）的全部组件与组合方式，数据均为虚构，不来自接口。新页面请从组件库组合，规范见
        docs/ui-components.md。
      </Alert>

      <SectionTitle
        title="指标卡 MetricCard"
        actions={
          <Segmented
            label="统计区间"
            value={range}
            options={[
              { value: "7", label: "近 7 天" },
              { value: "30", label: "近 30 天" },
            ]}
            onChange={setRange}
          />
        }
      />
      <div className="uk-metrics">
        <MetricCard
          featured
          label="本月已开票金额（CNY）"
          value="1,245,000.00"
          icon="amount"
          delta={{ text: "12.5%", direction: "up", tone: "positive", caption: "较上月" }}
          sparkline={TOTAL}
        />
        <MetricGrid label="开票指标">
          <MetricCard
            label="待开票任务"
            value="38"
            icon="invoice"
            delta={{ text: "3.2%", direction: "down", tone: "positive", caption: "较上周" }}
          />
          <MetricCard
            label="待通知供应商"
            value="12"
            icon="bell"
            delta={{ text: "4", direction: "up", tone: "negative", caption: "较上周" }}
          />
          <MetricCard
            label="待收金额（CNY）"
            value="326,480.00"
            icon="chart"
            sparkline={[30, 28, 31, 27, 26, 24, 25, 22]}
            delta={{ text: "8.1%", direction: "down", tone: "positive", caption: "较上周" }}
          />
          <MetricCard label="资料待补齐" value="5" icon="contract" hint="多为回签合同未上传" />
          <MetricCard
            label="平均等待天数"
            value="6.4"
            unit="天"
            icon="clock"
            delta={{ text: "持平", direction: "flat", tone: "neutral" }}
          />
          <MetricCard
            label="本月任务完成率"
            value="72.0%"
            icon="check"
            footer={<Gauge percent={72} label="本月任务完成率" />}
          />
        </MetricGrid>
      </div>

      <SectionTitle title="流程分区条 StageTabs" />
      <StageTabs
        label="按流程阶段筛选（演示）"
        value={stage}
        onChange={setStage}
        total={{ label: "进行中任务", count: 38, hint: "未完成、未被替代" }}
        items={[
          { key: "documents", label: "待存合同", count: 3, hint: "合同未全部归档" },
          { key: "notification", label: "待通知供应商", count: 12, hint: "合同已就绪" },
          { key: "invoices", label: "待供应商开票", count: 18, hint: "已通知未收票" },
          { key: "comparison", label: "部分收票", count: 3, hint: "仍有行未结束" },
          { key: "completion", label: "待补资料", count: 2, hint: "资料未到齐" },
          { key: "done", label: "已完成", count: 41, hint: "收齐且归档", terminal: true },
        ]}
      />

      <SectionTitle title="图表 TrendChart / DonutChart" />
      <div className="uk-charts">
        <Card>
          <CardHeader
            title="已开票金额趋势"
            description="按开票日期，单位：万元"
            actions={<Button>查看进项发票</Button>}
          />
          <CardContent>
            <TrendChart
              label="已开票金额趋势（演示）"
              categories={DAYS}
              line={{ key: "total", label: "合计", values: TOTAL, texts: wan(TOTAL) }}
              bars={[
                { key: "lemon", label: "柠檬云拉取", values: LEMON, texts: wan(LEMON) },
                { key: "manual", label: "人工比对", values: MANUAL, texts: wan(MANUAL) },
                { key: "excel", label: "Excel 导入", values: EXCEL, texts: wan(EXCEL) },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader title="任务节点分布" description="进行中任务" />
          <CardContent>
            <DonutChart
              label="任务节点分布（演示）"
              centerLabel="进行中"
              centerValue="38"
              segments={[
                { key: "invoices", label: "待供应商开票", value: 18, text: "18 个" },
                { key: "notification", label: "待通知供应商", value: 12, text: "12 个" },
                { key: "completion", label: "待补资料", value: 5, text: "5 个" },
                { key: "comparison", label: "部分收票", value: 3, text: "3 个" },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      <SectionTitle title="状态与流程 Badge / Stepper / Progress / Segmented / Alert" />
      <Card>
        <CardContent className="uk-stack">
          <div className="uk-row">
            <Badge tone="warning">待通知供应商</Badge>
            <Badge tone="info">待供应商开票</Badge>
            <Badge tone="progress">部分收票</Badge>
            <Badge tone="success">开票完成</Badge>
            <Badge tone="danger">下载失败</Badge>
            <Badge tone="neutral">已被替代</Badge>
          </div>
          <Stepper label="任务节点（演示）" steps={STEPS} />
          <div className="uk-row">
            <Progress width="62.5" text="62.5%" label="收票金额进度" />
            <Progress width="100" text="100%" label="收票金额进度" tone="success" />
            <Segmented
              label="节点筛选（演示）"
              value={node}
              onChange={setNode}
              options={[
                { value: "all", label: "全部", count: 38 },
                { value: "notify", label: "待通知", count: 12 },
                { value: "invoice", label: "待开票", count: 18 },
              ]}
            />
          </div>
          <div className="uk-alerts">
            <Alert tone="info">任务按财务审核通过时冻结的应开数量和金额跟进。</Alert>
            <Alert tone="danger" title="暂不能推进">
              采购来源或开票依据已变化，请重新审核后操作。
            </Alert>
          </div>
        </CardContent>
      </Card>

      <SectionTitle
        title="查询与表格 FilterBar / DataTable / Pagination"
        count="共 4 条"
        actions={
          <Button>
            <Icon name="download" /> 导出
          </Button>
        }
      />
      <Card>
        <CardContent>
          <FilterBar
            onSubmit={() => undefined}
            actions={
              <>
                <Button variant="primary" type="submit">
                  查询
                </Button>
                <Button>清除</Button>
              </>
            }
          >
            <Field label="报关单 / 供应商" grow>
              <input type="search" placeholder="CD10086 或供应商名称" />
            </Field>
            <Field label="供应商">
              <select defaultValue="">
                <option value="">全部供应商</option>
              </select>
            </Field>
          </FilterBar>
        </CardContent>
        <DataTable
          label="开票任务（演示）"
          rowKey={(row) => row.id}
          rows={ROWS}
          columns={[
            {
              key: "supplier",
              header: "供应商",
              width: "28%",
              render: (row) => <strong>{row.supplier}</strong>,
            },
            { key: "record", header: "报关单", render: (row) => row.record },
            { key: "stage", header: "当前节点", render: (row) => <Badge tone={row.tone}>{row.stage}</Badge> },
            { key: "amount", header: "待收金额（CNY）", align: "right", render: (row) => row.amount },
            {
              key: "progress",
              header: "收票进度",
              render: (row) => (
                <Progress width={row.progress} text={`${row.progress}%`} label="收票金额进度" />
              ),
            },
            { key: "action", header: "操作", align: "right", render: () => <Button>跟进详情</Button> },
          ]}
        />
        <CardFooter>
          <Pagination
            label="演示分页"
            total={4}
            page={1}
            pageCount={1}
            pageSize={20}
            pageSizes={[10, 20, 50]}
            onPageChange={() => undefined}
            onPageSizeChange={() => undefined}
          />
        </CardFooter>
      </Card>

      <SectionTitle title="紧凑对照表 DataTable" />
      <Card>
        <DataTable
          label="紧凑来源对照（演示）"
          density="compact"
          rowKey={(row) => row.id}
          rowTone={(row) => (row.accent ? "accent" : undefined)}
          rows={[
            {
              id: "a",
              source: "来源 A",
              name: "演示商品",
              quantity: "20.0000",
              amount: "100.00",
              accent: false,
            },
            {
              id: "b",
              source: "来源 B",
              name: "演示商品",
              quantity: "20.0000",
              amount: "120.00",
              accent: true,
            },
          ]}
          columns={[
            { key: "source", header: "来源", render: (row) => row.source },
            { key: "name", header: "品名", render: (row) => row.name },
            { key: "quantity", header: "数量", align: "right", render: (row) => row.quantity },
            { key: "amount", header: "金额（CNY）", align: "right", render: (row) => row.amount },
          ]}
        />
      </Card>

      <SectionTitle title="弹窗 Dialog / 批量上传 BatchUpload" />
      <Card>
        <CardContent className="uk-stack">
          <p>
            Dialog 打开后焦点进入弹窗、提交期间不能关闭；BatchUpload
            分批提交文件并逐个展示后端结果，识别不了归属的文件可填写编号重传。
          </p>
          <span>
            <Button onClick={() => setDialog("dialog")}>打开弹窗</Button>{" "}
            <Button onClick={() => setDialog("upload")}>打开批量上传</Button>
          </span>
        </CardContent>
      </Card>
      {dialog === "dialog" && (
        <Dialog title="演示弹窗" onClose={() => setDialog("")}>
          <p>弹窗正文与操作区；按 Esc 或“关闭”退出，焦点回到触发按钮。</p>
        </Dialog>
      )}
      {dialog === "upload" && (
        <BatchUpload
          title="演示批量上传"
          help="演示：不会提交文件。文件名含 8 位以上数字视为已识别编号。"
          accept=".pdf,.jpg,.jpeg,.png"
          targetLabel="编号"
          targetMaxLength={100}
          statusLabels={{ saved: "已保存", unmatched: "未识别编号" }}
          assignable={["unmatched"]}
          upload={demoUpload}
          onClose={() => setDialog("")}
        />
      )}

      <SectionTitle title="请求状态 EmptyState / ErrorState / Skeleton" />
      <div className="uk-states">
        <Card>
          <EmptyState
            title="当前条件下没有任务"
            description="可切换节点或清除搜索条件查看其他任务。"
            action={<Button>查看全部</Button>}
          />
        </Card>
        <Card>
          <ErrorState
            title="数据暂时无法加载"
            message="后端服务暂时不可用，请稍后重新加载。"
            action={<Button>重新加载</Button>}
          />
        </Card>
        <Card>
          <Skeleton label="正在读取数据" rows={2} />
        </Card>
      </div>
    </div>
  );
}
