import type { SidebarGroup } from "../shared/components/Sidebar";
import type { View } from "./paths";

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

// 所有页面共用的导航，按岗位分组（财务 / 采购 / 系统），不携带模拟业务计数。
export const navigation: readonly SidebarGroup<View>[] = [
  {
    label: "工作空间",
    items: [
      {
        id: "workbench",
        label: "总体工作台",
        icon: <MenuIcon path="M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z" />,
      },
    ],
  },
  {
    label: "财务",
    items: [
      {
        id: "finance",
        label: "财务核对",
        icon: <MenuIcon path="M9 11l3 3 8-8 M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11" />,
      },
      {
        id: "match",
        label: "发票比对",
        icon: <MenuIcon path="M4 7h13l-3-3 M20 17H7l3 3" />,
      },
      {
        id: "invoices",
        label: "进项发票",
        icon: <MenuIcon path="M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6" />,
      },
    ],
  },
  {
    label: "采购",
    items: [
      {
        id: "invoice-followup",
        label: "开票跟进",
        icon: <MenuIcon path="M4 4h4v16H4z M10 4h4v10h-4z M16 4h4v7h-4z" />,
      },
      {
        id: "supplier-profiles",
        label: "供应商档案",
        icon: <MenuIcon path="M4 21V4h11v17 M15 9h5v12 M7 8h4 M7 12h4 M7 16h4 M2 21h20" />,
      },
      {
        id: "pl",
        label: "采购报关联查",
        icon: <MenuIcon path="M3 4h18v16H3z M3 9h18 M3 14h18 M9 4v16" />,
      },
    ],
  },
  {
    label: "系统",
    items: [
      {
        id: "sync",
        label: "数据同步",
        icon: (
          <MenuIcon path="M20 11a8 8 0 0 0-14.6-4.5L3 9 M3 3v6h6 M4 13a8 8 0 0 0 14.6 4.5L21 15 M21 21v-6h-6" />
        ),
      },
      {
        id: "writeback",
        label: "NS 回写",
        icon: <MenuIcon path="M4 12h12 M12 6l6 6-6 6 M20 4v16" />,
      },
      {
        id: "ui-kit",
        label: "界面组件库",
        icon: <MenuIcon path="M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M16.5 13v7 M13 16.5h7" />,
      },
    ],
  },
];
