import "./progress-ring.css";

/** 单值环形展示；value 和 text 直接使用后端值，不计算业务比例。 */
export function ProgressRing({ value, text, label }: { value: string; text: string; label: string }) {
  return (
    <span className="ui-progress-ring" role="img" aria-label={`${label}：${text}`}>
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <circle className="ui-progress-ring__track" cx="32" cy="32" r="27" />
        <circle
          className="ui-progress-ring__value"
          cx="32"
          cy="32"
          r="27"
          pathLength="100"
          strokeDasharray={`${value} 100`}
          transform="rotate(-90 32 32)"
        />
      </svg>
      <strong>{text}</strong>
    </span>
  );
}
