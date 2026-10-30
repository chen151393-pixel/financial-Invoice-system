import type { ReactNode } from "react";
import "./sync.css";
import { SyncOverview } from "./SyncOverview";

/** 数据同步页内容区：同步中心显示平台概览，NS 与柠檬云页由调用方传入各自工作区。 */
export default function SyncPage({
  source,
  children,
}: {
  source: "ns" | "lemon" | "overview";
  children?: ReactNode;
}) {
  return <div className="sync-page">{source === "overview" ? <SyncOverview /> : children}</div>;
}
