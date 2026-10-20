/** 后端回写接口尚未登记时的占位：说明限制，不显示示例数据，也不呈现为加载中。 */
export function NotConnected({ scope }: { scope: string }) {
  return (
    <section className="wb-panel wb-not-connected" aria-labelledby="wb-not-connected-title">
      <h2 id="wb-not-connected-title">NS 回写尚未接入</h2>
      <p>后端回写接口与 NS 写入脚本还没有实现，{scope}</p>
      <ul>
        <li>不能查询可回写的发票，也不能生成预览或写入 NS。</li>
        <li>本页不显示示例数据；接入后将展示后端返回的真实记录与校验结果。</li>
        <li>需要登记到 NS 的发票，暂时仍在 NS“供应商发票勾选平台”中手工处理。</li>
      </ul>
    </section>
  );
}
