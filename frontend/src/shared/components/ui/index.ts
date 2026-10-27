// 统一组件库唯一入口：业务页面只从这里组合界面（规范见 docs/ui-components.md）。
// 组件只负责展示与交互，不含发票、审批等领域逻辑，不计算金额或判断业务是否允许。
import "./ui.css";

export { Badge, type Tone } from "./Badge";
export { BatchUpload, type BatchUploadFile, type BatchUploadResult } from "./BatchUpload";
export { Card, CardContent, CardFooter, CardHeader, SectionTitle } from "./Card";
export { DataTable, type Column } from "./DataTable";
export { Dialog } from "./Dialog";
export { Field, FilterBar } from "./FilterBar";
export { Icon, type IconName } from "./Icon";
export { MetricCard, MetricGrid, type MetricDelta } from "./MetricCard";
export { Progress } from "./Progress";
export { Segmented } from "./Segmented";
export { StageTabs, type StageItem } from "./StageTabs";
export { StatCard, StatGrid, type StatTone } from "./StatCard";
export { Alert, EmptyState, ErrorState, Skeleton } from "./States";
export { Stepper, type StepItem } from "./Stepper";
export { Tabs } from "./Tabs";
export { DonutChart, type DonutSegment } from "./charts/DonutChart";
export { Gauge } from "./charts/Gauge";
export { Sparkline } from "./charts/Sparkline";
export { TrendChart, type ChartSeries } from "./charts/TrendChart";
// 已有公共组件同样从此处导出，页面只需一个导入来源
export { Button } from "../Button";
export { Pagination } from "../Pagination";
