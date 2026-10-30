import { useEffect, useState } from "react";
import { openLocalSession } from "../identity/api";
import { Button } from "../../shared/components/Button";
import { getSources, type Sources, type SourceKind } from "./api";
import { PullPanel } from "./PullPanel";
import "./sync.css";

/** NS 手动拉取：左侧选择单据类型，右侧按日期拉取并查看本次结果。各类型面板只隐藏不卸载，切换不中断拉取。 */
export function NsManualPull() {
  const [pulling, setPulling] = useState(false);
  const [sources, setSources] = useState<Sources | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selectedKind, setSelectedKind] = useState<SourceKind>("customs-declarations");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getSources();
        if (active) {
          setSources(data);
          setError("");
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取配置失败");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [attempt]);
  if (error)
    return (
      <div role="alert" className="sync-page__panel">
        <p>{error}</p>
        <Button
          onClick={() => {
            setError("");
            setAttempt((value) => value + 1);
          }}
        >
          重新加载配置
        </Button>
      </div>
    );
  if (!sources) return <p role="status">正在读取连接配置…</p>;
  return (
    <div className="sync-page sync-page--ns">
      <div className="sync-page__workspace">
        <fieldset className="sync-page__selector" disabled={pulling}>
          <legend>单据类型</legend>
          <div className="sync-page__choices">
            {sources.sources.map((item) => (
              <label
                key={item.kind}
                className="sync-page__choice"
                htmlFor={`sync-kind-${item.kind}`}
                aria-label={item.label}
              >
                <input
                  id={`sync-kind-${item.kind}`}
                  type="radio"
                  name="ns-document-kind"
                  value={item.kind}
                  checked={selectedKind === item.kind}
                  onChange={() => setSelectedKind(item.kind)}
                />
                <span>
                  <strong>{item.label}</strong>
                  <small
                    className="sync-page__kind-tag"
                    data-level={item.storageAllowed ? "save" : item.allowed ? "read" : "off"}
                  >
                    {item.storageAllowed ? "可保存" : item.allowed ? "仅读取" : "暂不可拉取"}
                  </small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {sources.sources.length === 0 && <p role="status">尚未配置可展示的 NS 单据类型。</p>}
        {sources.sources.map((item) => (
          <div key={item.kind} className="sync-page__result-slot" hidden={selectedKind !== item.kind}>
            <PullPanel source={item} onBusyChange={setPulling} />
          </div>
        ))}
      </div>
    </div>
  );
}
