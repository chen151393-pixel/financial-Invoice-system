import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  SectionTitle,
  Skeleton,
  Tabs,
} from "../../../shared/components/ui";
import { BoardNodeCards } from "../components/BoardNodeCards";
import type { TaskBoardQuery } from "../types/board";
import { DemoFollowupRow } from "./DemoFollowupRow";
import { demoNodes, followupPresets } from "./followup-presets";
import { demoTasks } from "./workflow-data";
import "../pages/task-board.css";
import "./workflow-demo.css";

type PreviewState = "ready" | "loading" | "empty" | "error";

/** 基于现有开票跟进的独立原型；只筛选虚构样例，不发起业务请求。 */
export function WorkflowDemoPage() {
  const [node, setNode] = useState<TaskBoardQuery["node"]>("");
  const [keyword, setKeyword] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [previewState, setPreviewState] = useState<PreviewState>("ready");
  const [revision, setRevision] = useState(0);
  const rows = demoTasks.filter(
    (task) =>
      (!node || followupPresets[task.id].node === node) &&
      (!category || task.category === category) &&
      `${task.supplier} ${task.order} ${task.declaration}`
        .toLowerCase()
        .includes(submittedKeyword.toLowerCase()),
  );
  function reset() {
    setNode("");
    setKeyword("");
    setSubmittedKeyword("");
    setCategory("");
    setPreviewState("ready");
    setRevision((value) => value + 1);
  }
  return (
    <div className="tb task-demo">
      <Alert tone="info" title="基于现有开票跟进的优化示例">
        保留节点分区与任务行，增加承诺日期、候选发票入口和行内处理。全部为虚构数据，不保存业务、不发送通知；样例日期为
        2026-10-26。
      </Alert>
      <SectionTitle
        title="任务节点"
        actions={
          <Button size="sm" variant="ghost" onClick={reset}>
            重置演示
          </Button>
        }
      />
      <BoardNodeCards nodes={demoNodes} openTotal={5} value={node} onChange={setNode} />
      <FilterBar
        onSubmit={() => setSubmittedKeyword(keyword.trim())}
        pending={keyword.trim() !== submittedKeyword ? "关键词修改后点击查询" : undefined}
        actions={<Button type="submit">查询样例</Button>}
      >
        <Field label="供应商 / 报关单 / 子采购单" grow>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="例如：澄川、DEMO-PO-0861"
          />
        </Field>
        <Field label="需要处理的事项">
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">全部事项</option>
            <option value="review">候选发票待核对</option>
            <option value="followup">跟进开票日期</option>
            <option value="documents">补齐归档资料</option>
          </select>
        </Field>
      </FilterBar>
      <SectionTitle
        title={node ? demoNodes.find((item) => item.key === node)!.label : "全部进行中"}
        count={previewState === "ready" ? rows.length : undefined}
        actions={<span className="task-demo__muted">流程按需展开 · 直接在当前行处理</span>}
      />
      {previewState === "loading" && (
        <Card>
          <Skeleton label="演示：正在读取开票跟进" rows={5} />
        </Card>
      )}
      {previewState === "error" && (
        <Card>
          <ErrorState
            title="开票跟进暂时无法读取（演示）"
            message="查询条件已保留，可重新读取列表。"
            action={<Button onClick={() => setPreviewState("ready")}>演示重新读取</Button>}
          />
        </Card>
      )}
      {(previewState === "empty" || (previewState === "ready" && !rows.length)) && (
        <Card>
          <EmptyState
            title="当前条件下没有任务"
            description="筛选条件继续保留，可调整条件查看其他样例。"
            action={<Button onClick={reset}>恢复全部样例</Button>}
          />
        </Card>
      )}
      <div hidden={previewState !== "ready" || !rows.length} key={revision}>
        <Card className="tb-list">
          {rows.map((task) => (
            <DemoFollowupRow key={task.id} task={task} />
          ))}
        </Card>
      </div>
      <details className="task-demo__preview-controls">
        <summary>演示说明与页面状态</summary>
        <p>
          候选发票与有效收票分开展示；节点、进度、金额和超期均为固定样例。顶部节点数量为全部样例分布，列表另按处理事项和关键词筛选。关闭行内处理会清空该行演练输入。
        </p>
        <Tabs
          label="演示页面状态"
          value={previewState}
          onChange={setPreviewState}
          items={[
            { key: "ready", label: "正常数据" },
            { key: "loading", label: "加载中" },
            { key: "empty", label: "空结果" },
            { key: "error", label: "请求失败" },
          ]}
        />
      </details>
    </div>
  );
}
