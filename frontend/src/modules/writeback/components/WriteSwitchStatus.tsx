import type { WriteSwitch } from "../types";

/** 写入开关与账套来自后端；开关关闭时仍可生成预览，但执行按钮由后端 allowed 控制。 */
export function WriteSwitchStatus({ write }: { write: WriteSwitch }) {
  return (
    <p className="wb-switch" role="status">
      <span>
        NS 写入：
        <strong className={write.enabled ? "wb-switch__on" : "wb-switch__off"}>
          {write.enabled ? "已启用" : "未启用"}
        </strong>
      </span>
      <span className="wb-muted">
        {write.account} · {write.reason}
      </span>
    </p>
  );
}
