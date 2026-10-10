import { useNavigate } from "react-router";
import { type View, viewPath } from "./paths";

// 侧栏点击在应用内切换页面，不整页刷新。
export function useViewNavigate() {
  const navigate = useNavigate();
  return (view: View) => navigate(viewPath(view));
}
