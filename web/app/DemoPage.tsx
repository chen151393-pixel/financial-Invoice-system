import { useEffect, useRef } from "react";
import Demo from "../../app/page";
import "../../app/globals.css";

export default function DemoPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  const bannerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const banner = bannerRef.current;
    if (!banner) return;
    const resize = new ResizeObserver(() => {
      rootRef.current?.style.setProperty("--demo-banner-height", `${banner.offsetHeight}px`);
    });
    resize.observe(banner);
    return () => resize.disconnect();
  }, []);

  return (
    <div className="demo-page" ref={rootRef}>
      <div className="demo-label" ref={bannerRef}>
        界面演示：所有业务数据和连接状态均为模拟，按钮不会操作 NS。
        <a href="/">返回真实 NS 操作</a>
      </div>
      <Demo />
    </div>
  );
}
