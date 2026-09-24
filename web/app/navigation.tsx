import type { SidebarGroup } from "../shared/components/Sidebar";
import type { View } from "./views";

function MenuIcon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}

// 所有页面共用的导航，不携带模拟业务计数。
export const navigation: readonly SidebarGroup<View>[] = [
  {
    label: "发票管理",
    items: [
      {
        id: "dashboard",
        label: "发票工作台",
        icon: <MenuIcon path="M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z" />,
      },
      {
        id: "invoices",
        label: "进项发票",
        icon: <MenuIcon path="M5 3h14v18l-3-2-4 2-4-2-3 2z M8 8h8 M8 12h8" />,
      },
      {
        id: "match",
        label: "自动匹配",
        icon: <MenuIcon path="M3 6h5l8 12h5 M17 14l4 4-4 4 M3 18h5l3-4 M14 10l2-4h5 M17 2l4 4-4 4" />,
      },
      {
        id: "exceptions",
        label: "异常处理",
        icon: <MenuIcon path="M12 4l10 17H2z M12 10v4 M12 17v.1" />,
      },
    ],
  },
  {
    label: "集成与控制",
    items: [
      {
        id: "sync",
        label: "数据同步",
        icon: <MenuIcon path="M20 10a8 8 0 0 0-14-4L3 9 M3 3v6h6 M4 14a8 8 0 0 0 14 4l3-3 M15 15h6v6" />,
      },
      {
        id: "finance",
        label: "财务核对",
        icon: <MenuIcon path="M5 12l4 4L19 6" />,
      },
      {
        id: "invoice-followup",
        label: "开票跟进",
        icon: <MenuIcon path="M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h5" />,
      },
      {
        id: "pl",
        label: "采购报关联查",
        icon: <MenuIcon path="M3 4h18v16H3z M3 9h18 M3 14h18 M9 4v16" />,
      },
      {
        id: "reconcile",
        label: "系统对账",
        icon: <MenuIcon path="M3 7h17 M16 3l4 4-4 4 M21 17H4 M8 13l-4 4 4 4" />,
      },
      {
        id: "writeback",
        label: "回写 NetSuite",
        icon: <MenuIcon path="M4 20L20 4 M9 4h11v11" />,
      },
    ],
  },
];
