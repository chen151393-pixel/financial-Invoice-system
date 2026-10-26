import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "sm";
};
export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  type = "button",
  ...props
}: Props) {
  return (
    <button
      {...props}
      type={type}
      className={`ui-button ui-button--${variant}${size === "sm" ? " ui-button--sm" : ""} ${className}`}
    />
  );
}
