export type Op = "=" | "gte" | "lte" | "in" | "includes";
export interface Requirement { id: string; field: string; op: Op; value: string; unit: string; mandatory: boolean; note: string }
export interface Spec {
  field: string; value: string; unit: string; raw: string; file: string; page: number;
  display?: string | null; rangeMin?: number | null; rangeMax?: number | null; note?: string | null;
  extractedBy: string; confirmed: boolean; confirmedBy?: string | null; confirmedAt?: string | null;
}
export interface Cert {
  authority: string; certNo: string; validUntil: string; file: string; page: number;
  extractedBy: string; confirmed: boolean; confirmedBy?: string | null; confirmedAt?: string | null;
}
export type Expected = "MATCH" | "CHECK" | "EXCLUDED";
export type RestrictionKind = "PROHIBITED" | "CONDITIONAL" | "ADVISORY";
export interface Restriction {
  kind: RestrictionKind; contexts: string[]; materials: string[]; scope_other?: string | null; summary: string; quote: string;
  file: string; page: number; note?: string | null; key: string; extractedBy: string; confirmed: boolean; confirmedBy?: string | null; confirmedAt?: string | null;
}
export interface RestrictionFinding {
  level: "BLOCK" | "CAUTION"; kind: RestrictionKind; summary: string; reason: string; contexts: string[]; quote: string; file: string; page: number;
  extractedBy?: string | null; confirmedBy?: string | null; confirmedAt?: string | null;
}
export interface Product {
  id: string; manufacturer: string; model: string; leadTime: number | null;
  leadTimeSource: string; leadTimeCheckedAt: string; scenario: string; expected: Expected | null;
  synthetic: boolean; partType: string; real: { label: string; url: string } | null; specs: Spec[]; certs: Cert[]; restrictions: Restriction[];
}
export interface Project {
  project_id: string; ship_name: string; class_society: string; system: string; part_type: string; need_by_date: string;
  ship_type: string; hull_no: string; replace_model: string; replace_reason: string; is_synthetic: string;
}
export type Status = "PASS" | "FAIL" | "UNKNOWN";
export interface Evidence { file: string; page: number; raw: string; extractedBy?: string | null; confirmedBy?: string | null; confirmedAt?: string | null }
export interface ReqResult { req: Requirement; status: Status; actual: string; reason: string; evidence?: Evidence | null }
export interface Delivery { status: Status; days: number | null; need: number; reason: string; source: string }
export interface Evaluation {
  restrictions: RestrictionFinding[]; restrictionsReviewed: number; items: ReqResult[]; overall: Expected; failed: ReqResult[]; unknown: ReqResult[]; optionalMiss: ReqResult[]; delivery: Delivery;
}
export interface Bootstrap {
  partTypes: string[]; contexts: Record<string, string>; systemContexts: Record<string, string[]>; projects: Project[]; requirementsByProject: Record<string, Requirement[]>; products: Product[]; docs: string[]; samples: string[];
  llm: { available: boolean; model: string; cli: boolean };
}
export interface Extraction {
  file: string; method: "rules" | "llm" | "cli"; pageCount: number; specs: Spec[]; certs: Cert[]; restrictions: Restriction[];
  notes: { page: number; text: string }[]; warnings: string[]; flagged: string[]; model?: string | null;
}
export interface Metrics {
  total: number; agree: number; falsePass: number; falseExcluded: number; excludedCount: number;
  checkOk: number; checkTotal: number; judged: number; linked: number;
  rows: { id: string; model: string; scenario: string; expected: Expected; actual: Expected; real: boolean }[];
}
