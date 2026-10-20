import type { WritebackRequest } from "../types";

/** 写入前校验由后端完成；这里只列出结果，未通过项附后端原因。 */
export function PreviewChecks({ checks }: { checks: WritebackRequest["checks"] }) {
  const failed = checks.filter((check) => !check.passed).length;
  return (
    <section className="wb-panel" aria-labelledby="wb-checks-title">
      <h2 id="wb-checks-title" className="wb-section-title">
        写入前校验
        <span className={failed ? "wb-note--failed" : "wb-note--succeeded"}>
          {failed ? ` · ${failed} 项未通过` : ` · ${checks.length} 项全部通过`}
        </span>
      </h2>
      <ul className="wb-checks">
        {checks.map((check) => (
          <li key={check.label}>
            <span className={check.passed ? "wb-check wb-check--pass" : "wb-check wb-check--fail"}>
              {check.passed ? "通过" : "未通过"}
            </span>
            <span>{check.label}</span>
            {check.detail && <span className="wb-muted">{check.detail}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
