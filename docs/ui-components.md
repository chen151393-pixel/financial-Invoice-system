# 统一组件库（shared/components/ui）

## 单值环形展示与分页计量单位（2026-10-28）

- `ProgressRing`：传 `value`（后端 0–100 字符串）、`text` 与 `label`，显示完整圆环和中心文本，不计算业务比例。用于发票比对置信度；样式独立在 `progress-ring.css`，不改变已有图表。
- `Pagination` 新增可选 `unit`，默认“条”；整票审核队列传“张”，同步用于总数及每页选项。其他页面保持原来的默认单位。

状态：2026-10-25 建立。新页面和改版页面的界面**只从本组件库组合**；旧页面在被修改时逐步迁移，不为迁移单独重写。视觉基准见 [design.md](../design.md)，工程规范见 [前端统一规范](frontend-conventions.md)。

- 代码位置：`frontend/src/shared/components/ui/`，唯一入口 `index.ts`。
- 2026-10-28 已移除“界面组件库”展示页及侧栏入口；共享组件继续供业务页面复用，使用方式以本文和组件类型定义为准。
- 风格参考：ProBoost 后台（白底卡片、浅灰画布、主色图标块、左侧竖条分区标题、堆叠柱 + 折线趋势图、环形占比图）。颜色、圆角、字体仍使用本项目 `tokens.css`，保持与其他页面一致；未引入 Tailwind、shadcn CLI 或图表依赖，图表为 SVG 实现。

## 使用方式

`Field` 默认显示上方标签；仅需输入框内提示时传 `hideLabel`，标签仍为读屏提供名称，不影响其他页面默认布局。

```tsx
import { Card, CardHeader, CardContent, MetricCard, MetricGrid, Badge } from "../../../shared/components/ui";
```

1. 先在本库中找组件；确实缺少时**在本库新增**（带中文注释、加入 `index.ts` 并更新本文），不在业务页面里自造同类样式。
2. 业务页面 CSS 只做排布（grid、间距、列宽），不覆盖 `.ui-*` 的颜色、字号、圆角。
3. 业务状态到颜色的映射写在业务模块（如任务台 `NODE_TONES`），组件只接收 `tone`。
4. 组件不计算金额、占比、差额，不判断业务是否允许；数值与文案来自后端。图表的 `values` 只用于绘图位置，提示与图例显示后端给出的文本。

## 组件清单

`HorizontalBarChart` 展示非负计数的横向条形图：`items` 提供 `key/label/value/text`，可选 `color/note`。统一零刻度，零值不画色条，数量显示在条末；小屏将附注置于条形下方。

| 组件                                                 | 用途                         | 要点                                                                                                                                         |
| ---------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `SectionTitle`                                       | 页面分区标题（左侧主色竖条） | 可带数量 `count` 与右侧 `actions`                                                                                                            |
| `Card` / `CardHeader` / `CardContent` / `CardFooter` | 内容面板                     | 按头、内容、底部组合；`CardContent flush` 用于表格贴边                                                                                       |
| `MetricCard` / `MetricGrid`                          | 指标卡与栅格                 | `featured` 主色主指标（一屏最多一个；`true` 浅主色底，`"solid"` 主色实底白字，用于总览页头号指标）；`badge` 右上角标签（如财务 / 采购）；`delta.tone` 由调用方按业务含义指定（`warning` 为需关注）；`onSelect`+`selected` 时作为筛选按钮；可带 `sparkline`、`footer` |
| `StatCard` / `StatGrid`                              | 概况卡与栅格                 | 一个字的图块 + 标签 + 数值 + 说明；`tone`：neutral / warning（积压提醒）/ primary（合计）；`compact` 一行排开多张；`onSelect`+`selected` 作筛选；`StatGrid min` 设最小列宽 |
| `Badge`                                              | 状态徽标                     | `tone`：warning 待处理、info 等外部、progress 部分完成、success 已完成、danger 失败/阻塞、neutral 已替代                                     |
| `StageTabs`                                          | 流程分区条                   | 按流程顺序横排各阶段（数量 + 说明），阶段间箭头连接，左侧可放合计；`terminal` 终态不画箭头；窄屏换行为多列                                   |
| `Tabs`                                               | 下划线标签                   | 同一区域的状态筛选或视图切换（全部 / 待审核 / 审核通过），可带计数；放在卡片顶部时由页面去掉自身底线                                         |
| `Segmented`                                          | 2–7 个互斥选项               | 如近 7 天 / 近 30 天、节点切换，可带计数                                                                                                     |
| `Progress`                                           | 进度条                       | `width` 为后端 0–100 展示宽度，`text` 为后端实际值文本                                                                                       |
| `Stepper`                                            | 流程节点                     | 状态由后端判定；`compact` 用于列表行内；传 `onSelect`+`selectedKey` 时节点可点击（详情页切换分区）；读屏附带“已完成/当前节点/未开始”         |
| `FilterBar` / `Field`                                | 查询条件栏                   | 标签在上；`pending` 提示条件已改未提交；`Field grow` 用于关键字；`embedded` 放在列表卡片标题下方，去掉自身边框                              |
| `DataTable`                                          | 数据表                       | 列定义 `align: "right"` 用于金额数量；宽表容器内横向滚动；不在前端排序汇总                                                                   |
| `EmptyState` / `ErrorState` / `Skeleton` / `Alert`   | 请求状态与提示               | 空结果、失败、加载、就近提示各用其一，不混用                                                                                                 |
| `TrendChart`                                         | 趋势图                       | 堆叠柱 `bars` + 折线 `line`；悬停提示；附读屏数据表；不用于含负数序列                                                                        |
| `DonutChart`                                         | 环形占比                     | 中心合计 + 图例，图例文本由调用方给出                                                                                                        |
| `Sparkline` / `Gauge`                                | 迷你走势、半圆仪表           | 只表达形状或单一比率                                                                                                                         |
| `Dialog`                                             | 模态弹窗                     | 焦点进入弹窗、背景不可操作，关闭后回到触发控件；`busy` 时不能关闭                                                                             |
| `BatchUpload`                                        | 批量上传窗口                 | 复用 FileDropzone 选择／拖入、追加与移除文件；只显示本次结果、路径折叠、重开清空；每批立即展示并保留中途失败前的结果；`assignable` 状态可填写编号重传；格式与归属由后端判断。 |
| `FileDropzone` | 文件选择与拖入 | 整块区域点击或键盘选择，支持多选、文件拖入高亮与禁用状态；选择和拖入统一回调，不判断业务格式、大小或归属，取消选择保留原列表。 |
| `Icon`                                               | 线性图标                     | 新图标在 `Icon.tsx` 登记，不在页面手画                                                                                                       |
| `Button` / `Pagination`                              | 既有公共组件                 | `Button` 支持 `primary` / `secondary` / `ghost` 与 `size="sm"`；同样从本入口导出                                                             |

设计变量新增：`--color-primary-soft`、`--color-primary-strong`、`--shadow-card`、`--color-chart-1`…`5`、`--color-chart-line`、`--color-chart-grid`（`tokens.css`）。配色收在主蓝与侧栏海军蓝一个色系内（2026-10-26 调整）：图表系列用主蓝、浅蓝、淡蓝、蓝灰的深浅区分，折线用海军蓝；主指标卡为浅主色底；流程当前节点用主色描边。大面积不使用橙、绿、紫等跳色，语义色只用于状态徽标、提示框等小面积。

## 页面使用情况（2026-10-27）

页面外壳（`AppFrame`）为固定格式白色页头：面包屑、标题、一句说明 `description`，右侧只放只读信息 `meta`（如数据来源）；业务按钮一律放在页面内容里。

已从组件库组合：开票跟进（`StatCard compact` 节点卡、列表卡片内嵌 `FilterBar embedded`、任务卡片）、任务详情（概览 + 当前节点卡片 + 应开明细 + 右侧资料与记录）、财务核对（`StatCard` 概况、列表卡片 + `Segmented` 状态切换 + 内嵌查询栏、紧凑来源对照表）、进项发票（指标卡、`TrendChart`/`DonutChart`/`Progress` 分布图、列表卡片）、比对审核队列、供应商档案、总体工作台（待办标签）、NS 回写列表、发票比对详情（2026-10-28：`Card` 票面 + 紧凑 `DataTable` 商品明细 + `Badge`，下方左右分栏核对）。外部群导入、数据同步、采购报关联查仍为原页面样式，修改时迁移。

## 紧凑表格与行底色

`DataTable` 默认外观不变；`density="compact"` 使用 12px 正文与紧凑单元格留白，`rowTone(row)` 返回 `"accent"` 时使用项目浅蓝对照底色。调用方同时提供来源文字，不能只用底色区分。列宽与数值对齐仍由 `columns` 控制，顺序由后端数据决定。

## 首个使用者

`DataTable` 可选 `maxHeight` 接受 CSS 最大高度（数字按 px 或 CSS 字符串），开启表内纵向滚动和固定表头；横向与纵向共用一个可键盘聚焦的滚动区域。不传时沿用原有布局。

开票跟进 `/tasks`（原采购开票任务台，`frontend/src/modules/task/pages/TaskBoardPage.tsx`）：`StatCard`（节点卡，2026-10-27 起替代 `StageTabs`）、`Card`+`CardHeader`+`FilterBar embedded`（列表卡片）、`Badge`+`Stepper`+`Progress`+`Alert`（每个任务的状态与默认展开流程）、`Skeleton`/`EmptyState`/`ErrorState`、`Pagination`。旧 `/tasks/board` 重定向到 `/tasks`。

## 验证

以下为历史验证记录，涉及的组件展示页已于 2026-10-28 移除。

2026-10-25 在本地隔离 SQLite（合成数据）预览：`/ui-kit` 与 `/tasks/board` 在 1440px 与 375px 下检查，无页面横向溢出；任务台节点筛选与地址同步、来源变化提示、已完成分区可用。未做浏览器以外的视觉回归基线；暗色模式未适配（项目当前无暗色主题）。

## 2026-10-27 补充

- `TrendChart` 新增 `grouped`（并排柱）与 `lineAxis="percent"`（折线按右侧百分比轴绘制，轴上限至少 100%，超过时随真实最大值扩展并在点上显示 `texts`，“—”不标注）；系列可传 `color`（设计变量）。
- `TrendChart.line.values` 支持 `null`：不画该点、不跨空值连线，提示文字由 `texts` 提供。各月份支持 Tab 聚焦查看明细，并提供焦点边框；金额轴和百分比轴保持真实比例。
- `Sparkline` 新增 `warning`、`inverse`（实底卡片上反白）色调。
- 设计变量新增 `--color-warning`：超期、需关注等小面积标记（条形、走势线），不用于大面积底色。

### SearchInput 批量查询输入

`SearchInput` 复用查询栏原生输入样式，使用 `value` / `onValueChange` 管理草稿；粘贴换行或制表符时转换为分号保留条目边界，后端负责拆分、去重和数量限制。配合 `<Field label="供应商" hideLabel grow>` 仅显示框内提示，同时保留读屏标签。当前用于供应商档案和财务报关单搜索；输入框回车提交所属 `FilterBar`。
