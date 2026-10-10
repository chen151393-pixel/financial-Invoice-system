export function FinanceIcon({ kind }: { kind: "chevron" | "check" | "clock" | "alert" }) {
  const paths = {
    chevron: "M8 5l7 7-7 7",
    check: "M5 12l4 4L19 6",
    clock: "M12 8v4l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    alert: "M12 8v5 M12 17v.1 M12 3L2 21h20z",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[kind]} />
    </svg>
  );
}
