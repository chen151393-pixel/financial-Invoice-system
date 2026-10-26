// 线性图标：与侧栏菜单同一风格（24 网格、1.6 描边），尺寸随父级字号。新增图标在此登记，不在业务页面手画。
const PATHS = {
  amount:
    "M12 3v18 M16.5 7.5c0-1.7-2-3-4.5-3s-4.5 1.3-4.5 3 2 3 4.5 3.5 4.5 1.8 4.5 3.5-2 3-4.5 3-4.5-1.3-4.5-3",
  invoice: "M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6 M9 16h3",
  contract: "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h5 M10 16h5",
  bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4z M10 20a2 2 0 0 0 4 0",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2",
  check: "M5 12l4 4L19 6",
  alert: "M12 3l10 18H2z M12 10v4 M12 17.5v.5",
  chart: "M4 20V4 M4 20h16 M8 16v-4 M12 16V8 M16 16v-6",
  trendUp: "M4 17l6-6 4 4 6-7 M15 8h5v5",
  trendDown: "M4 7l6 6 4-4 6 7 M15 16h5v-5",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4",
  download: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
  truck:
    "M3 6h11v10H3z M14 10h4l3 3v3h-7 M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  users:
    "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M2 21a7 7 0 0 1 14 0 M16 3.5a4 4 0 0 1 0 7 M22 21a7 7 0 0 0-4-6.3",
  refresh: "M20 10a8 8 0 0 0-14-4L3 9 M3 3v6h6 M4 14a8 8 0 0 0 14 4l3-3 M15 15h6v6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, label }: { name: IconName; label?: string }) {
  return (
    <svg
      className="ui-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
