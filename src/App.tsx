import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Bootstrap, Evaluation, Product, Project, Requirement } from "./types";
import { ProjectView, RequirementsView } from "./views1";
import { CandidatesView, CompareView } from "./views2";
import { MetricsView, ReportView } from "./views3";
import { RegisterModal, ShipModal, UploadModal } from "./views4";

const stored = () => { try { return localStorage.getItem("marine_who") || "담당자"; } catch { return "담당자"; } };
const STEPS = ["프로젝트·부품", "검색 조건", "후보 탐색", "비교·근거", "검토 보고서"];

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);
  const [reqs, setReqs] = useState<Requirement[]>([]);
  const [evals, setEvals] = useState<Record<string, Evaluation>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [metrics, setMetrics] = useState(false);
  const [register, setRegister] = useState(false);
  const [upload, setUpload] = useState<Product | null>(null);
  const [toast, setToast] = useState("");
  const [pid, setPid] = useState("");
  const [shipModal, setShipModal] = useState(false);
  const seq = useRef(0);
  const saved = useRef("");          // 마지막으로 서버에 저장된 요구조건(JSON)
  const project = boot?.projects.find((p) => p.project_id === pid) ?? boot?.projects[0];
  const classesOf = (id: string) => {   // 그 선박의 요구조건에서 인정 선급 목록을 읽는다(현재 선박은 편집 중인 값)
    const rs = id === project?.project_id ? reqs : boot?.requirementsByProject[id] ?? [];
    return rs.find((r) => r.field === "class_approval")?.value ?? "";
  };
  const partProducts = (boot?.products ?? []).filter((p) => p.partType === project?.part_type);   // 후보는 선택한 부품 종류의 제품만

  const pidRef = useRef("");
  useEffect(() => { pidRef.current = pid; }, [pid]);

  const activate = useCallback((id: string, next: Requirement[]) => {
    saved.current = JSON.stringify(next);
    pidRef.current = id;
    setPid(id); setReqs(next); setSelected([]); setEvals({});
    try { localStorage.setItem("marine_project", id); } catch { /* ignore */ }
  }, []);

  const refresh = useCallback(async () => {
    const b = await api.bootstrap();
    setBoot(b);
    if (!pidRef.current || !b.projects.some((p) => p.project_id === pidRef.current)) {   // 최초 로드·삭제 후: 저장된 선택 또는 첫 선박
      let want = "";
      try { want = localStorage.getItem("marine_project") ?? ""; } catch { /* ignore */ }
      const id = b.projects.some((p) => p.project_id === want) ? want : b.projects[0].project_id;
      activate(id, b.requirementsByProject[id]);
    }
    return b;
  }, [activate]);

  /** 선박 전환. 전환 전 미저장 수정은 서버에 저장하고 로컬 캐시에도 반영한다. */
  const selectProject = useCallback((id: string, b?: Bootstrap, reqsOf?: Requirement[]) => {
    const base = b ?? boot;
    if (!base || (id === pid && !b)) return;
    let cache = base.requirementsByProject;
    if (pid && cache[pid] && JSON.stringify(reqs) !== saved.current) {
      api.saveRequirements(pid, reqs).catch(() => undefined);
      cache = { ...cache, [pid]: reqs };
    }
    const next = reqsOf ?? cache[id];
    setBoot({ ...base, requirementsByProject: { ...cache, [id]: next } });
    activate(id, next);
  }, [boot, pid, reqs, activate]);

  useEffect(() => { refresh().catch((e) => setError(String(e.message ?? e))); }, [refresh]);

  useEffect(() => {  // 요구조건 수정은 선박별로 자동 저장(디바운스)
    if (!pid || !reqs.length) return;
    const json = JSON.stringify(reqs);
    if (json === saved.current) return;
    const t = setTimeout(() => api.saveRequirements(pid, reqs).then(() => {
      saved.current = json;
      setBoot((cur) => (cur ? { ...cur, requirementsByProject: { ...cur.requirementsByProject, [pid]: reqs } } : cur));
    }).catch((e) => setError(String(e.message ?? e))), 600);
    return () => clearTimeout(t);
  }, [pid, reqs]);

  useEffect(() => {  // 요구조건 또는 제품 데이터가 바뀌면 서버 엔진으로 재판정
    if (!boot || !reqs.length) return;
    const n = ++seq.current;
    const t = setTimeout(() => api.evaluate(reqs, project?.system ?? "").then((r) => { if (n === seq.current) setEvals(r.evaluations); }).catch((e) => setError(String(e.message ?? e))), 120);
    return () => clearTimeout(t);
  }, [boot?.products, reqs, project?.part_type, project?.system]);

  const say = (m: string) => { setToast(m); setTimeout(() => setToast(""), 5000); };
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 3 ? [...s.slice(1), id] : [...s, id]));

  if (error && !boot) return (
    <div className="boot"><h2>백엔드에 연결할 수 없습니다</h2><p className="muted">{error}</p>
      <pre>cd backend && .venv/bin/uvicorn app.main:app --port 8000</pre>
      <button className="btn primary" onClick={() => { setError(""); refresh().catch((e) => setError(String(e.message ?? e))); }}>다시 시도</button></div>);
  if (!boot || !project) return <div className="boot"><p className="muted">불러오는 중…</p></div>;

  return (
    <div className="app">
      <header className="top no-print">
        <div className="brand"><span className="logo">⚓</span><div><b>MARINE MATCH</b><small>선박 요구조건 기반 대체 기자재 검토</small></div></div>
        <nav className="steps">{STEPS.map((s, i) => (
          <button key={s} className={`${i === step ? "on" : ""} ${i < step ? "done" : ""}`} onClick={() => setStep(i)}><i>{i + 1}</i>{s}</button>))}</nav>
        <div className="right"><button className="cur-ship" title="선박 변경" onClick={() => setStep(0)}>🚢 {project.ship_name} · {classesOf(project.project_id).split("|").join("/") || project.class_society}</button>
          <span className="chip chip-neutral">가상 + 공개 문서 예시</span>
          <button className="btn ghost sm" onClick={() => setMetrics(true)}>검증 지표</button>
          <button className="btn ghost sm" title="업로드·확정 내역을 지우고 시연 데이터로 되돌립니다" onClick={async () => { if (confirm("업로드·확정한 데이터를 지우고 시연 데이터로 되돌릴까요?")) { await api.reset(); pidRef.current = ""; await refresh(); say("시연 데이터로 초기화했습니다."); } }}>초기화</button></div>
      </header>
      {error && <div className="err-bar no-print">{error} <button onClick={() => setError("")}>✕</button></div>}
      <main>
        {step === 0 && <ProjectView projects={boot.projects} current={project} classesOf={classesOf} contexts={boot.contexts} systemContexts={boot.systemContexts} partTypes={boot.partTypes} reqCount={reqs.length} partCount={partProducts.length}
          onUpdate={async (patch) => { try { await api.updateProject(project.project_id, patch); await refresh(); setSelected([]); say(`교체 대상 기자재를 '${patch.part_type}'(으)로 변경했습니다.`); } catch (e) { setError(String((e as Error).message)); } }} onSelect={(id) => selectProject(id)} onNew={() => setShipModal(true)} onNext={() => setStep(1)}
          onDelete={async (p: Project) => { if (!confirm(`선박 '${p.ship_name}'을 삭제할까요? 이 선박의 요구조건도 함께 삭제됩니다.\n(기자재 DB의 제품은 삭제되지 않습니다.)`)) return;
            try { await api.deleteProject(p.project_id); const b = await api.bootstrap(); if (p.project_id === pid) selectProject(b.projects[0].project_id, b); else setBoot(b); say(`선박 '${p.ship_name}'을 삭제했습니다.`); } catch (e) { setError(String((e as Error).message)); } }} />}
        {step === 1 && <RequirementsView reqs={reqs} setReqs={setReqs} onNext={() => setStep(2)} ship={project.ship_name} />}
        {step === 2 && <CandidatesView products={partProducts} partType={project.part_type} evals={evals} selected={selected} toggle={toggle} goCompare={() => setStep(3)} onRegister={() => setRegister(true)}
          onDelete={async (p: Product) => { if (!confirm(`제품 '${p.manufacturer} ${p.model}'을 기자재 DB에서 삭제할까요?\n확정한 사양·인증과 업로드한 문서도 함께 삭제됩니다. (모든 선박에 영향)`)) return;
            try { await api.deleteProduct(p.id); setSelected((sel) => sel.filter((x) => x !== p.id)); await refresh(); say(`제품 '${p.model}'을 삭제했습니다.`); } catch (e) { setError(String((e as Error).message)); } }} />}
        {step === 3 && <CompareView contexts={boot.contexts} system={project.system} products={partProducts} evals={evals} selected={selected} docs={boot.docs} toggle={toggle} openUpload={setUpload}
          setLead={async (p, d) => { await api.leadTime(p.id, d, "담당자"); await refresh(); say(`${p.model}: 납기 ${d}일을 기록했습니다.`); }} goReport={() => setStep(4)}
          onDeleteRestriction={async (p, key) => { if (!confirm(`'${p.model}'의 사용 제한 해석을 삭제할까요? 판정에서 더 이상 대조되지 않습니다.`)) return; try { await api.deleteRestriction(p.id, key, stored()); await refresh(); say("사용 제한을 삭제했습니다."); } catch (e) { setError(String((e as Error).message)); } }}
          onDeleteSpec={async (p, f) => { if (!confirm(`'${p.model}'의 확정 자료를 삭제할까요? 해당 항목은 ‘확인 필요’로 되돌아갑니다.`)) return; try { await api.deleteSpec(p.id, f, stored()); await refresh(); say("확정 자료를 삭제했습니다."); } catch (e) { setError(String((e as Error).message)); } }}
          onDeleteCert={async (p, no) => { if (!confirm(`'${p.model}'의 인증서 ${no}를 삭제할까요? 인증 조건은 ‘확인 필요’로 되돌아갑니다.`)) return; try { await api.deleteCert(p.id, no, stored()); await refresh(); say("인증서를 삭제했습니다."); } catch (e) { setError(String((e as Error).message)); } }} />}
        {step === 4 && <ReportView project={project} reqs={reqs} products={partProducts} evals={evals} selected={selected} />}
      </main>
      {toast && <div className="toast no-print">{toast}</div>}
      {shipModal && <ShipModal projects={boot.projects} currentId={project.project_id} partTypes={boot.partTypes} onClose={() => setShipModal(false)}
        onCreated={async (p, r) => { setShipModal(false); const b = await api.bootstrap(); selectProject(p.project_id, b, r); say(`선박 '${p.ship_name}'을 등록했습니다. ${p.class_society} 선급 기준으로 요구조건을 만들었습니다.`); setStep(1); }} />}
      {metrics && <MetricsView onClose={() => setMetrics(false)} />}
      {register && <RegisterModal partTypes={boot.partTypes} defaultType={project.part_type} onClose={() => setRegister(false)} onCreated={async (p) => { setRegister(false); const b = await refresh(); setUpload(b.products.find((x) => x.id === p.id) ?? p); }} />}
      {upload && <UploadModal key={upload.id} product={boot.products.find((p) => p.id === upload.id) ?? upload} boot={boot} onClose={() => setUpload(null)} onDocs={async () => { await refresh(); }}
        onConfirmed={async (m) => { await refresh(); setUpload(null); setSelected((s) => (s.includes(upload.id) ? s : [...s, upload.id].slice(-3))); say(m); }} />}
    </div>
  );
}
