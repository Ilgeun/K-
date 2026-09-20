import { useState } from "react";
import type { Bootstrap, Cert, Extraction, Product, Project, Requirement, RestrictionKind, Spec } from "./types";
import { api } from "./api";
import { FIELD_LABEL, KIND_TEXT, fmtVal } from "./format";
import { Chip, EvidenceDrawer, METHOD_TEXT } from "./components";
import { REASONS } from "./views1";

const today = () => new Date().toISOString().slice(0, 10);
const specText = (s: Spec) => s.display ?? fmtVal(s.value, s.unit);
const stored = (): string => { try { return localStorage.getItem("marine_who") || "담당자"; } catch { return "담당자"; } };

export function RegisterModal({ partTypes, defaultType, onClose, onCreated }: { partTypes: string[]; defaultType: string; onClose: () => void; onCreated: (p: Product) => void }) {
  const [mfr, setMfr] = useState(""); const [model, setModel] = useState(""); const [ptype, setPtype] = useState(defaultType); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true); setErr("");
    try { onCreated(await api.createProduct(mfr, model, ptype)); } catch (e) { setErr(String((e as Error).message)); setBusy(false); }
  };
  return (
    <div className="drawer-bg center" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>제품 등록</h3>
        <p className="muted small">제조사 문서(PDF)에서 사양을 추출해 기자재 DB에 추가합니다. 등록 후 바로 문서를 올립니다.</p>
        <label className="field">제조사<input value={mfr} onChange={(e) => setMfr(e.target.value)} placeholder="예: Korea Unicomvalve" /></label>
        <label className="field">부품 종류<select value={ptype} onChange={(e) => setPtype(e.target.value)}>{partTypes.map((x) => <option key={x}>{x}</option>)}</select></label>
        <label className="field">모델명<input value={model} onChange={(e) => setModel(e.target.value)} placeholder="예: High-Seal GTD" /></label>
        {err && <div className="why">{err}</div>}
        <div className="actions"><button className="btn ghost" onClick={onClose}>취소</button>
          <button className="btn primary" disabled={!mfr.trim() || !model.trim() || busy} onClick={go}>등록하고 문서 올리기 →</button></div>
      </div>
    </div>
  );
}

export function UploadModal({ product, boot, onClose, onDocs, onConfirmed }: {
  product: Product; boot: Bootstrap; onClose: () => void; onDocs: () => Promise<void>; onConfirmed: (msg: string) => Promise<void>;
}) {
  const [phase, setPhase] = useState<"choose" | "busy" | "review">("choose");
  const [mode, setMode] = useState("auto");
  const [sample, setSample] = useState(boot.samples[0] ?? "");
  const [ex, setEx] = useState<Extraction | null>(null);
  const [pickS, setPickS] = useState<boolean[]>([]); const [pickC, setPickC] = useState<boolean[]>([]);
  const [pickR, setPickR] = useState<boolean[]>([]); const [kinds, setKinds] = useState<RestrictionKind[]>([]);
  const [err, setErr] = useState(""); const [who, setWho] = useState(stored()); const [ok, setOk] = useState(false);
  const [view, setView] = useState<{ file: string; page: number; raw: string } | null>(null);

  const handle = async (run: () => Promise<Extraction>) => {
    setPhase("busy"); setErr("");
    try {
      const r = await run();
      await onDocs();
      setEx(r); setPickS(r.specs.map((s) => s.value !== "UNKNOWN" && !r.flagged.includes(s.field))); setPickC(r.certs.map((c) => !r.flagged.includes(`cert:${c.certNo}`))); setPickR(r.restrictions.map((x) => !r.flagged.includes(`restriction:${x.key}`))); setKinds(r.restrictions.map((x) => x.kind)); setPhase("review");
    } catch (e) { setErr(String((e as Error).message)); setPhase("choose"); }
  };
  const confirm = async () => {
    if (!ex) return;
    setPhase("busy");
    try { localStorage.setItem("marine_who", who); } catch { /* ignore */ }
    try {
      const specs = ex.specs.filter((_, i) => pickS[i]); const certs = ex.certs.filter((_, i) => pickC[i]);
      const rests = ex.restrictions.map((r, i) => ({ ...r, kind: kinds[i] })).filter((_, i) => pickR[i]);
      await api.confirm(product.id, specs, certs, who.trim() || "담당자", rests);
      await onConfirmed(`${product.model}: 사양 ${specs.length}건·인증 ${certs.length}건·사용 제한 ${rests.length}건을 확정하고 재평가했습니다.`);
    } catch (e) { setErr(String((e as Error).message)); setPhase("review"); }
  };
  const nSel = pickS.filter(Boolean).length + pickC.filter(Boolean).length + pickR.filter(Boolean).length;

  return (
    <div className="drawer-bg center" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head"><h3>문서 업로드 · 추출 — {product.manufacturer} {product.model}</h3><button className="btn ghost" onClick={onClose}>닫기 ✕</button></div>

        {phase !== "review" && <>
          <div className="llm-line">{boot.llm.available ? <Chip kind="match">Claude API 연결됨 · {boot.llm.model}</Chip>
              : boot.llm.cli ? <Chip kind="match">Claude CLI 사용 가능 (로그인 계정)</Chip> : <Chip kind="check">Claude 없음 → 규칙 기반 추출로 동작</Chip>}
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="auto">추출 방식: 자동</option>{boot.llm.available && <option value="llm">Claude API</option>}{boot.llm.cli && <option value="cli">Claude CLI</option>}<option value="rules">규칙 기반</option></select></div>
          <div className="grid2">
            <div className="card"><b>내 PDF 올리기</b><p className="muted small">제조사 데이터시트나 선급 형식승인서(PDF, 20MB 이하)</p>
              <input type="file" accept="application/pdf" disabled={phase === "busy"} onChange={(e) => { const f = e.target.files?.[0]; if (f) handle(() => api.upload(product.id, f, mode)); }} /></div>
            <div className="card"><b>샘플 문서로 시연</b><p className="muted small">가상 샘플 PDF (워터마크 표시)</p>
              <select value={sample} onChange={(e) => setSample(e.target.value)} style={{ maxWidth: "100%" }}>{boot.samples.map((s) => <option key={s}>{s}</option>)}</select>{" "}
              <button className="btn primary sm" disabled={phase === "busy" || !sample} onClick={() => handle(() => api.sample(product.id, sample, mode))}>추출 시작</button></div>
          </div>
          {phase === "busy" && <div className="note">문서를 읽고 사양을 추출하는 중입니다…</div>}
          {err && <div className="why">{err}</div>}
        </>}

        {phase === "review" && ex && <>
          <div className="llm-line"><Chip kind={ex.method === "rules" ? "neutral" : "match"}>{METHOD_TEXT[ex.method]}{ex.model ? ` · ${ex.model}` : ""}</Chip>
            <span className="muted small">{ex.file} · {ex.pageCount}쪽</span></div>
          {ex.warnings.map((w, i) => <div className="why warn" key={i}>⚠ {w}</div>)}
          {ex.specs.length + ex.certs.length + ex.restrictions.length === 0 && <div className="empty">추출된 항목이 없습니다.</div>}
          <table className="table"><thead><tr><th></th><th>항목</th><th>추출 값</th><th>현재 등록</th><th>근거</th></tr></thead><tbody>
            {ex.specs.map((s, i) => { const cur = product.specs.find((x) => x.field === s.field);
              return <tr key={"s" + i}><td><input type="checkbox" checked={pickS[i]} onChange={() => setPickS(pickS.map((v, j) => (j === i ? !v : v)))} /></td>
                <td><b>{FIELD_LABEL[s.field] ?? s.field}</b>{ex.flagged.includes(s.field) && <div><Chip kind="check">⚠ 검증 필요 (기본 제외)</Chip></div>}</td><td>{specText(s)}{s.note && <div className="small muted">{s.note}</div>}</td>
                <td className="muted">{cur ? specText(cur) : "자료 없음"}</td>
                <td><button className="link" onClick={() => setView({ file: s.file, page: s.page, raw: s.raw })}>p.{s.page}</button><div className="small muted q">“{s.raw}”</div></td></tr>; })}
            {ex.certs.map((c: Cert, i) => { const expired = c.validUntil < today();
              return <tr key={"c" + i}><td><input type="checkbox" checked={pickC[i]} onChange={() => setPickC(pickC.map((v, j) => (j === i ? !v : v)))} /></td>
                <td><b>선급 형식승인</b></td><td>{c.authority} · {c.certNo} · ~{c.validUntil} {expired ? <Chip kind="excluded">만료됨</Chip> : <Chip kind="match">유효</Chip>}</td>
                <td className="muted">{product.certs.length ? product.certs.map((x) => `${x.authority} ${x.certNo}`).join(", ") : "자료 없음"}</td>
                <td><button className="link" onClick={() => setView({ file: c.file, page: c.page, raw: `${c.authority} 형식승인 ${c.certNo} (유효 ${c.validUntil})` })}>p.{c.page}</button></td></tr>; })}
          </tbody></table>
          {ex.restrictions.length > 0 && <div className="restr-box">
            <h4>사용 제한 조건 <span className="chip chip-real">{ex.method === "rules" ? "규칙 기반 해석" : "AI 해석"}</span></h4>
            <p className="muted small">문서의 제한 문장을 읽고 ‘어떤 계통에서, 어떤 재질에, 어떤 수준으로’ 제한되는지 구조화했습니다. <b>원문과 대조해 확정한 것만</b> 선박의 사용 계통에 규칙으로 대조됩니다.
              {ex.method === "rules" && " 규칙 기반 해석은 조건을 놓치거나 과하게 읽을 수 있어 기본 선택하지 않았습니다."}</p>
            <table className="table"><thead><tr><th></th><th>수준</th><th>해당 계통</th><th>적용 범위</th><th>요약 · 원문</th></tr></thead><tbody>
              {ex.restrictions.map((r, i) => <tr key={r.key}>
                <td><input type="checkbox" checked={pickR[i] ?? false} onChange={() => setPickR(pickR.map((v, j) => (j === i ? !v : v)))} /></td>
                <td><select value={kinds[i]} onChange={(e) => setKinds(kinds.map((k, j) => (j === i ? (e.target.value as RestrictionKind) : k)))}>
                  {(Object.keys(KIND_TEXT) as RestrictionKind[]).map((k) => <option key={k} value={k}>{KIND_TEXT[k]}</option>)}</select></td>
                <td>{r.contexts.map((c) => <span key={c} className="chip chip-neutral" style={{ marginRight: 4 }}>{boot.contexts[c] ?? c}</span>)}</td>
                <td className="small">{r.materials.length ? <div>재질: {r.materials.join(", ")}</div> : <div className="muted">제품 전체</div>}{r.scope_other && <div>조건: {r.scope_other}</div>}</td>
                <td><b>{r.summary}</b><div><button className="link" onClick={() => setView({ file: r.file, page: r.page, raw: r.quote })}>p.{r.page}</button></div>
                  <div className="small muted q2">“{r.quote}”</div>{r.note && <div className="small muted">{r.note}</div>}</td></tr>)}
            </tbody></table></div>}
          {ex.notes.length > 0 && <div className="note"><b>문서에서 발견된 제한 문구</b>{ex.notes.map((n, i) => <div key={i} className="small">p.{n.page} · {n.text}</div>)}</div>}
          <div className="confirm-row">
            <label>확인자 <input value={who} onChange={(e) => setWho(e.target.value)} style={{ width: 130 }} /></label>
            <label className="confirm"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> 선택한 값을 원문과 대조하여 확인했습니다</label>
          </div>
          {err && <div className="why">{err}</div>}
          <div className="actions"><button className="btn ghost" onClick={() => { setPhase("choose"); setEx(null); setOk(false); }}>다른 문서</button>
            <button className="btn primary" disabled={!ok || nSel === 0} onClick={confirm}>확정 및 재평가 ({nSel}건)</button></div>
        </>}
      </div>
      {view && ex && <div onClick={(e) => e.stopPropagation()}><EvidenceDrawer product={product} ev={view} docs={[...boot.docs, ex.file]} onClose={() => setView(null)} /></div>}
    </div>
  );
}


const CLASSES = ["DNV", "KR", "ABS", "LR", "NK", "BV"];
const SYSTEMS = ["해수 냉각", "청수 냉각", "밸러스트", "소화", "연료유", "LNG 연료", "기타"];
const SHIP_TYPES = ["컨테이너선", "LNG운반선", "탱커", "벌크선", "자동차운반선", "기타"];
const plusDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

export function ShipModal({ projects, currentId, partTypes, onClose, onCreated }: {
  projects: Project[]; currentId: string; partTypes: string[]; onClose: () => void; onCreated: (p: Project, reqs: Requirement[]) => void;
}) {
  const [f, setF] = useState({ ship_name: "", hull_no: "", ship_type: SHIP_TYPES[0], class_society: "DNV", system: SYSTEMS[0], need_by_date: plusDays(90), copy_from: currentId, part_type: partTypes[0], replace_model: "", replace_reason: REASONS[0], also_accept: [] as string[] });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const toggleClass = (c: string) => setF({ ...f, also_accept: f.also_accept.includes(c) ? f.also_accept.filter((x) => x !== c) : [...f.also_accept, c] });
  const go = async () => {
    setBusy(true); setErr("");
    try { const r = await api.createProject(f); onCreated(r.project, r.requirements); } catch (e) { setErr(String((e as Error).message)); setBusy(false); }
  };
  return (
    <div className="drawer-bg center" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>새 선박 등록</h3>
        <p className="muted small">선급·계통·필요 납기일에 맞춰 요구조건이 만들어지고, 이후 ② 단계에서 수정할 수 있습니다.</p>
        <label className="field">선박명 *<input value={f.ship_name} onChange={(e) => set("ship_name", e.target.value)} placeholder="예: 대형 컨테이너선 C호" autoFocus /></label>
        <div className="row2">
          <label className="field">호선번호<input value={f.hull_no} onChange={(e) => set("hull_no", e.target.value)} placeholder="예: H-2031" /></label>
          <label className="field">선종<select value={f.ship_type} onChange={(e) => set("ship_type", e.target.value)}>{SHIP_TYPES.map((x) => <option key={x}>{x}</option>)}</select></label>
        </div>
        <div className="row2">
          <label className="field">적용 선급<select value={f.class_society} onChange={(e) => set("class_society", e.target.value)}>{CLASSES.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label className="field">사용 계통<select value={f.system} onChange={(e) => set("system", e.target.value)}>{SYSTEMS.map((x) => <option key={x}>{x}</option>)}</select></label>
        </div>
        <div className="field">추가로 인정하는 선급 <span className="muted small">(선택 — 주 선급 외에 이 선급의 승인도 인정)</span>
          <div className="checks" style={{ marginTop: 6 }}>{CLASSES.filter((c) => c !== f.class_society).map((c) => (
            <label key={c}><input type="checkbox" checked={f.also_accept.includes(c)} onChange={() => toggleClass(c)} /> {c}</label>))}</div></div>
        <div className="row2">
          <label className="field">교체 대상 기자재<select value={f.part_type} onChange={(e) => set("part_type", e.target.value)}>{partTypes.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label className="field">교체 사유<select value={f.replace_reason} onChange={(e) => set("replace_reason", e.target.value)}>{REASONS.map((x) => <option key={x}>{x}</option>)}</select></label>
        </div>
        <label className="field">기존 모델<input value={f.replace_model} onChange={(e) => set("replace_model", e.target.value)} placeholder="예: A사 SMV-200 (지연 중인 모델)" /></label>
        <div className="row2">
          <label className="field">필요 납기일<input type="date" value={f.need_by_date} min={plusDays(1)} onChange={(e) => set("need_by_date", e.target.value)} /></label>
          <label className="field">요구조건 복제 원본<select value={f.copy_from} onChange={(e) => set("copy_from", e.target.value)}>{projects.map((x) => <option key={x.project_id} value={x.project_id}>{x.ship_name}</option>)}</select></label>
        </div>
        <div className="note">재질·구경 등 세부 조건은 복제 원본을 따르고, <b>인정 선급</b>과 <b>필요 납기</b>만 이 선박에 맞게 조정됩니다. 나머지는 ② 단계에서 수정하세요.</div>
        {err && <div className="why">{err}</div>}
        <div className="actions"><button className="btn ghost" onClick={onClose}>취소</button>
          <button className="btn primary" disabled={!f.ship_name.trim() || busy} onClick={go}>등록하고 선택 →</button></div>
      </div>
    </div>
  );
}
