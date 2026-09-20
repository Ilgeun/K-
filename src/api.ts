import type { Bootstrap, Evaluation, Extraction, Metrics, Product, Project, Requirement, Restriction, Spec, Cert } from "./types";

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}
const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  bootstrap: () => call<Bootstrap>("/api/bootstrap"),
  evaluate: (requirements: Requirement[], system: string) => call<{ evaluations: Record<string, Evaluation> }>("/api/evaluate", json({ requirements, system })),
  metrics: () => call<Metrics>("/api/metrics"),
  createProduct: (manufacturer: string, model: string, part_type: string) => call<Product>("/api/products", json({ manufacturer, model, part_type })),
  deleteProduct: (pid: string) => call<{ ok: boolean }>(`/api/products/${pid}`, { method: "DELETE" }),
  deleteSpec: (pid: string, field: string, who: string) => call<Product>(`/api/products/${pid}/specs/${encodeURIComponent(field)}?who=${encodeURIComponent(who)}`, { method: "DELETE" }),
  deleteCert: (pid: string, certNo: string, who: string) => call<Product>(`/api/products/${pid}/certs/${certNo.split("/").map(encodeURIComponent).join("/")}?who=${encodeURIComponent(who)}`, { method: "DELETE" }),
  updateProject: (pid: string, patch: { part_type?: string; replace_model?: string; replace_reason?: string }) => call<Project>(`/api/projects/${pid}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  upload: (pid: string, file: File, mode: string) => {
    const fd = new FormData(); fd.append("file", file);
    return call<Extraction>(`/api/products/${pid}/documents?mode=${mode}`, { method: "POST", body: fd });
  },
  sample: (pid: string, name: string, mode: string) => call<Extraction>(`/api/products/${pid}/documents/sample?mode=${mode}`, json({ name })),
  confirm: (pid: string, specs: Spec[], certs: Cert[], confirmedBy: string, restrictions: Restriction[] = []) => call<Product>(`/api/products/${pid}/confirm`, json({ specs, certs, restrictions, confirmedBy })),
  deleteRestriction: (pid: string, key: string, who: string) => call<Product>(`/api/products/${pid}/restrictions/${key}?who=${encodeURIComponent(who)}`, { method: "DELETE" }),
  leadTime: (pid: string, days: number | null, who: string) => call<Product>(`/api/products/${pid}/lead-time`, json({ days, who })),
  createProject: (body: { ship_name: string; class_society: string; system: string; need_by_date: string; ship_type: string; hull_no: string; copy_from: string; part_type: string; replace_model: string; replace_reason: string; also_accept: string[] }) =>
    call<{ project: Project; requirements: Requirement[] }>("/api/projects", json(body)),
  saveRequirements: (pid: string, reqs: Requirement[]) => call<{ ok: boolean }>(`/api/projects/${pid}/requirements`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(reqs) }),
  deleteProject: (pid: string) => call<{ ok: boolean }>(`/api/projects/${pid}`, { method: "DELETE" }),
  reset: () => call<{ ok: boolean }>("/api/reset", { method: "POST" }),
};
export const docUrl = (file: string) => `/api/docs/${encodeURIComponent(file)}`;
