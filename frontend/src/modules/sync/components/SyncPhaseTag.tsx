/** 后台批次状态标签：文字来自后端 label，颜色按 phase 区分，不只靠颜色表达。 */
export function SyncPhaseTag({ phase, label }: { phase: string; label: string }) {
  return (
    <span className="sync-phase" data-phase={phase}>
      {label}
    </span>
  );
}
