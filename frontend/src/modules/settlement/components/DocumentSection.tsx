import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, SectionTitle } from "../../../shared/components/ui";

/** 同一套资料内容在批次独立页使用卡片，在原资料工作区沿用分区标题。 */
export function DocumentSection({
  panel,
  title,
  count,
  actions,
  children,
}: {
  panel: boolean;
  title: string;
  count: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return panel ? (
    <Card>
      <CardHeader title={title} description={<>共 {count} 份</>} actions={actions} />
      <CardContent className="settlement-detail">{children}</CardContent>
    </Card>
  ) : (
    <>
      <SectionTitle title={title} count={count} actions={actions} />
      {children}
    </>
  );
}
