import { http } from "../../../shared/api/http";
import type { Candidate, Candidates, Delivery, DeliveryPreview } from "../types/delivery";

const root = (id: string) => `/tasks/${id}/notification`;
export const getDeliveries = (id: string) => http<{ items: Delivery[] }>(`${root(id)}/delivery`);
export const previewDelivery = (id: string, revision: number, groupRevision: number) =>
  http<DeliveryPreview>(`${root(id)}/preview`, "POST", { revision, groupRevision });
export const submitDelivery = (id: string, preview: DeliveryPreview, requestId: string) =>
  http<Delivery>(`${root(id)}/submit`, "POST", {
    revision: preview.revision,
    groupRevision: preview.groupRevision,
    snapshotSha256: preview.snapshotSha256,
    requestId,
  });
export const refreshDelivery = (id: string, deliveryId: string) =>
  http<Delivery>(`${root(id)}/refresh`, "POST", { deliveryId });
export const getCandidates = (id: string, deliveryId: string) =>
  http<Candidates>(`${root(id)}/delivery/${deliveryId}/candidates`);
export const reconcileDelivery = (id: string, deliveryId: string, candidate: Candidate, reason: string) =>
  http<Delivery>(`${root(id)}/reconcile`, "POST", {
    deliveryId,
    candidateId: candidate.candidateId,
    evidenceSha256: candidate.evidenceSha256,
    reason,
  });
