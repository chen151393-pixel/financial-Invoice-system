import { Button } from "../../../shared/components/Button";

export function NotificationCopyButton({
  copied,
  disabled,
  onCopy,
}: {
  copied: boolean;
  disabled: boolean;
  onCopy: () => void;
}) {
  return (
    <Button
      className="task-notification-copy"
      disabled={disabled}
      aria-label={copied ? "已复制通知正文" : "复制通知正文"}
      title={copied ? "已复制" : "复制通知正文"}
      onClick={onCopy}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {copied ? (
          <path d="m5 12 4 4L19 6" />
        ) : (
          <>
            <rect x="8" y="8" width="12" height="12" rx="2" />
            <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
          </>
        )}
      </svg>
    </Button>
  );
}
