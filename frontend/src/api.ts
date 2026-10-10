import type {
  BatchPayload,
  ListSummary,
  Model,
  ModelListParams,
  ModelUpdatePayload,
  Stats,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Erreur ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getModels(params: ModelListParams = {}): Promise<Model[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.lists?.length) qs.set("lists", params.lists.join(","));
  if (params.printed !== undefined) qs.set("printed", String(params.printed));
  if (params.sort) qs.set("sort", params.sort);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<Model[]>(`/api/models${suffix}`);
}

export function getModel(id: number): Promise<Model> {
  return request<Model>(`/api/models/${id}`);
}

export function updateModel(id: number, patch: ModelUpdatePayload): Promise<unknown> {
  return request(`/api/models/${id}`, { method: "PUT", body: JSON.stringify(patch) });
}

export function getLists(): Promise<ListSummary[]> {
  return request<ListSummary[]>("/api/lists");
}

export function createList(name: string): Promise<ListSummary> {
  return request<ListSummary>("/api/lists", { method: "POST", body: JSON.stringify({ name }) });
}

export function renameList(id: number, name: string): Promise<unknown> {
  return request(`/api/lists/${id}`, { method: "PUT", body: JSON.stringify({ name }) });
}

export function deleteList(id: number): Promise<unknown> {
  return request(`/api/lists/${id}`, { method: "DELETE" });
}

export function setModelLists(id: number, listIds: number[]): Promise<unknown> {
  return request(`/api/models/${id}/lists`, {
    method: "PUT",
    body: JSON.stringify({ list_ids: listIds }),
  });
}

export function trashModel(id: number): Promise<unknown> {
  return request(`/api/models/${id}/trash`, { method: "POST" });
}

export function restoreModel(id: number): Promise<unknown> {
  return request(`/api/models/${id}/restore`, { method: "POST" });
}

export function deleteModelPermanently(id: number): Promise<unknown> {
  return request(`/api/models/${id}`, { method: "DELETE" });
}

export function getTrash(): Promise<Model[]> {
  return request<Model[]>("/api/trash");
}

export function batchAction(payload: BatchPayload): Promise<{ processed: number[]; skipped: number[] }> {
  return request("/api/models/batch", { method: "POST", body: JSON.stringify(payload) });
}

export function getStats(): Promise<Stats> {
  return request<Stats>("/api/stats");
}

export function openFolder(id: number): Promise<{ folder: string }> {
  return request(`/api/models/${id}/open-folder`, { method: "POST" });
}

export function openOrcaSlicer(id: number): Promise<unknown> {
  return request(`/api/models/${id}/open-orcaslicer`, { method: "POST" });
}
