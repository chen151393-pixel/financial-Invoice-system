import { useId, useRef, useState } from "react";
import { Icon } from "./Icon";
import "./file-dropzone.css";

/** 文件选择与拖入共用同一回调；格式、大小及业务校验由后端执行。 */
export function FileDropzone({
  label,
  hint,
  accept,
  multiple = false,
  disabled = false,
  onFiles,
}: {
  label: string;
  hint: string;
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}) {
  const hintId = useId();
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  return (
    <label
      className="ui-file-dropzone"
      data-dragging={(dragging && !disabled) || undefined}
      data-disabled={disabled || undefined}
      onDragEnter={(event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        depth.current += 1;
        if (!disabled) setDragging(true);
      }}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = disabled ? "none" : "copy";
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        if (!disabled && event.dataTransfer.files.length) onFiles(Array.from(event.dataTransfer.files));
      }}
    >
      <input
        type="file"
        multiple={multiple}
        accept={accept}
        disabled={disabled}
        aria-label={label}
        aria-describedby={hintId}
        onChange={(event) => {
          if (event.target.files?.length) onFiles(Array.from(event.target.files));
          event.target.value = "";
        }}
      />
      <span className="ui-file-dropzone__icon">
        <Icon name="contract" />
      </span>
      <strong>{dragging && !disabled ? "松开即可添加文件" : label}</strong>
      <span id={hintId}>{hint}</span>
    </label>
  );
}
