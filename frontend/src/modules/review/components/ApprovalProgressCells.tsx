import type { ReactNode } from "react";
import { Link } from "react-router";
import { Badge, Button, type Tone } from "../../../shared/components/ui";
import type { ApprovalProgress, ApprovalStatus, ReviewLinks } from "../approval-progress";

const TONES: Record<ApprovalStatus["status"], Tone> = {
  approved: "success",
  pending: "warning",
  changed: "warning",
  blocked: "neutral",
};

export function ApprovalProgressCells({
  progress,
  declarationNo,
  page,
  links,
  localAction,
  canReview,
  onReview,
  onDetails,
  expanded,
  financeFallback,
  customsFallback,
}: {
  progress?: ApprovalProgress | null;
  declarationNo: string;
  page: "finance" | "customs";
  links?: ReviewLinks;
  localAction?: ReactNode;
  canReview: boolean;
  onReview: () => void;
  onDetails: () => void;
  expanded: boolean;
  financeFallback?: ReactNode;
  customsFallback?: ReactNode;
}) {
  const step = progress?.nextStep;
  const localFirst = canReview && (step === page || step === "both");
  let cross: string | undefined;
  if (page === "finance" && (step === "customs" || step === "import" || (step === "both" && !localFirst))) {
    cross = links?.customs?.(declarationNo, step === "import");
  }
  if (page === "customs" && (step === "finance" || (step === "both" && !localFirst))) {
    cross = links?.finance?.(declarationNo);
  }
  const relatedLabel = page === "finance" ? "查看对应海关回执" : "查看对应财务核对";
  const linkLabel = step === "import" ? "导入海关回执" : relatedLabel;
  let related: string | undefined;
  if (progress?.linked && !cross) {
    if (page === "customs") {
      related = links?.finance?.(declarationNo);
    } else if (progress.status !== "created") {
      related = links?.customs?.(declarationNo);
    }
  }
  const taskIds = progress?.taskIds ?? [];
  const taskLink = taskIds.length === 1 ? links?.task?.(taskIds[0]) : undefined;
  let action: ReactNode;
  if (localFirst) {
    action = (
      <Button variant="primary" size="sm" onClick={onReview}>
        {page === "finance" ? "审核财务" : "审核通过"}
      </Button>
    );
  } else if (cross) {
    action = (
      <Link to={cross} className="ui-button ui-button--ghost ui-button--sm">
        {linkLabel}
      </Link>
    );
  } else if (step === "tasks" && taskLink) {
    action = (
      <Link to={taskLink} className="ui-button ui-button--ghost ui-button--sm">
        查看任务
      </Link>
    );
  } else if (progress) {
    action = (
      <Button variant="ghost" size="sm" onClick={onDetails} aria-expanded={expanded}>
        {expanded ? "收起详情" : taskIds.length && links?.task ? "查看任务" : "查看详情"}
      </Button>
    );
  }
  return (
    <>
      <td>
        {progress ? (
          <Badge tone={TONES[progress.finance.status]}>{progress.finance.label}</Badge>
        ) : (
          (financeFallback ?? "—")
        )}
      </td>
      <td>
        {progress ? (
          <Badge tone={TONES[progress.customs.status]}>{progress.customs.label}</Badge>
        ) : (
          (customsFallback ?? "—")
        )}
      </td>
      <td className="fr-invoice-progress">
        {progress ? (
          <>
            <strong>{progress.label}</strong>
            {progress.reason && <small>{progress.reason}</small>}
          </>
        ) : (
          "—"
        )}
      </td>
      <td className="fr-declaration-action">
        <div className="fr-next-action">
          {related && (
            <Link to={related} className="ui-button ui-button--ghost ui-button--sm">
              {relatedLabel}
            </Link>
          )}
          {action}
          {!localFirst && localAction}
        </div>
      </td>
    </>
  );
}

export function ApprovalProgressDetail({
  progress,
  links,
  page,
  declarationNo,
  showRelatedLink = true,
}: {
  progress?: ApprovalProgress | null;
  links?: ReviewLinks;
  page: "finance" | "customs";
  declarationNo: string;
  showRelatedLink?: boolean;
}) {
  if (!progress) return null;
  const messages = [
    progress.finance.reason && `财务审核：${progress.finance.reason}`,
    progress.customs.reason && `海关审核：${progress.customs.reason}`,
  ].filter(Boolean);
  const taskLink = links?.task;
  const related =
    showRelatedLink && progress.linked
      ? page === "finance"
        ? links?.customs?.(declarationNo)
        : links?.finance?.(declarationNo)
      : undefined;
  if (!messages.length && !related && (!taskLink || !progress.taskIds.length)) return null;
  return (
    <div className="fr-progress-detail">
      {messages.map((message) => (
        <p key={message}>{message}</p>
      ))}
      {related && (
        <Link to={related} className="ui-button ui-button--ghost ui-button--sm">
          {page === "finance" ? "查看对应海关回执" : "查看对应财务核对"}
        </Link>
      )}
      {taskLink &&
        progress.taskIds.map((id) => (
          <Link key={id} to={taskLink(id)} className="ui-button ui-button--secondary ui-button--sm">
            查看任务 #{id}
          </Link>
        ))}
    </div>
  );
}
