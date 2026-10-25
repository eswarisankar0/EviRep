"use strict";
// EviRep read-only dashboard. Every value from the server is rendered through
// esc() (or md(), which escapes before formatting); nothing is inserted raw.
const $main = document.getElementById("main");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = v => v === null || v === undefined || v === "" ? '<span class="muted">—</span>'
  : (typeof v === "number" ? esc(Number.isInteger(v) ? v : v.toFixed(4).replace(/0+$/,"").replace(/\.$/,""))
  : (typeof v === "object" ? '<span class="mono">' + esc(JSON.stringify(v)) + '</span>' : esc(v)));
// Readable labels for machine states; the exact code stays in the tooltip (title) for technical users.
// Meanings follow the producing code: run tracker (scripts/run_stage.py), conflict agent, reproducibility agent,
// clinical role review. "Run completed" is operational only: it is not "output checks passed" or "validated".
const LABELS = {
  SUCCESS: "Run completed", PARTIAL: "Completed with gaps", ADOPTED: "Recorded baseline (before run tracking)", STALE: "Inputs changed — rerun needed", VERIFIED_WITH_GAPS: "Current, some inputs not verifiable",
  FAILED: "Run failed", RUNNING: "Running", NOT_RUN: "Not yet run", UNTRACKED: "Not tracked", MODIFIED: "Changed outside a run",
  MISSING: "Output missing", UNKNOWN: "Unknown", EXITED: "Finished", SKIPPED_FRESH: "Skipped (up to date)",
  BLOCKED: "Blocked by a failed prerequisite", REFUSED: "Refused by a safeguard", NO_EVIDENCE: "No evidence found",
  ALLOWED: "Can run here", CONFIRM: "Runs after confirmation",
  DIRECT_CONTRADICTION: "Direct contradiction", STATISTICAL_DISAGREEMENT: "Same direction, different significance",
  CONTEXT_DIFFERENCE: "Differs in context", CROSS_DOMAIN_TENSION: "Tension across evidence types",
  UNCERTAIN_COMPARABILITY: "Comparability uncertain", NON_COMPARABLE: "Not comparable",
  NO_DISAGREEMENT_DETECTED: "No disagreement found", NO_COMPARABLE_PAIR: "No comparable pair", INSUFFICIENT: "Insufficient evidence",
  SUPPORTS: "Supports", OPPOSES: "Opposes", NULL_RESULT: "Null result", NEUTRAL: "Neutral", UNCLEAR: "Unclear",
  REPLICATED: "Independently replicated", REPLICATED_WITH_DISAGREEMENT: "Replicated, with disagreement",
  SINGLE_STUDY: "Single study", INCONSISTENT_SINGLE_STUDIES: "Inconsistent single studies", SECONDARY_ONLY: "Reviews only",
  INSUFFICIENT_METADATA: "Insufficient metadata", VERIFIED: "Verified",
  INCONSISTENT_WITHIN_GROUP: "Disagreement within one research group", NO_SHARED_INDICATOR: "No shared author or trial found",
  SHARED_TRIAL: "Same trial", SHARED_AUTHORS: "Shared authors", METADATA_MISSING: "Metadata missing", PLAUSIBLY_INDEPENDENT: "Plausibly independent",
  NO_BACKUP: "Not backed up", TIMEOUT: "Time limit exceeded",
  UNRESOLVED: "Awaiting human review", ADJUDICATED: "Human-adjudicated", KEYWORD_DECIDED: "Decided by keywords only",
  ALIAS_GAP: "Matched via another name", CHEMBL_ALIAS: "Matched via ChEMBL name", STRUCTURE_INSUFFICIENT: "Trial arms unclear",
  AUTO_VS_ADJUDICATION: "Automatic and human disagree",
  THERAPEUTIC_TEST: "drug under test", PROCEDURAL_CONTEXT: "used for a procedure", BACKGROUND_OTHERNAME: "background medication (other name)",
  COMPARATOR_ONLY: "comparator only", ACTUATES_OTHER_THERAPY: "actuates another therapy", PLACEBO_COMPARATOR: "placebo comparator arm",
  ACTIVE_COMPARATOR: "active comparator arm", NO_INTERVENTION: "no-intervention arm", SHAM_COMPARATOR: "sham comparator arm",
  CONDITION_REJECTED: "condition not Parkinson's", MATCHED: "matched", NO_MATCH: "no match", HIGH: "High", BLOCKER: "Blocker", MEDIUM: "Medium", LOW: "Low",
  available: "Outputs present", input_newer: "Input newer than output",
  POST_CUTOFF: "published after the 2020 cutoff", PRE_CUTOFF: "published before the 2020 cutoff", UNKNOWN_DATE: "date unknown",
};
const human = s => LABELS[s] || (/^[A-Z][A-Z0-9_]+$/.test(String(s ?? "")) ? String(s).replace(/_/g, " ").toLowerCase() : String(s ?? "").replace(/_/g, " "));
// Registry and role codes inside free text (e.g. "Arm A: PLACEBO_COMPARATOR") shown in words; the raw text stays in the source files.
// Agent/stage identifiers inside agent-written text are dropped for display (they stay in the saved output and in "Source and provenance").
const plainText = t => codeText(String(t ?? "").replace(/\s*\((?:agent |stage )?(?:10[a-h]|04p|05h|D-0\d\d)(?:[,;][^)]*)?\)/g, "").replace(/\b10[a-h](?: --all)?:\s*/g, "").replace(/\b10[a-h] status\b/g, "status").replace(/\bby stage 04p\b/g, "by the PubMed provenance stage").replace(/\bnot used by VPS\b/g, "not used by the score").replace(/\bVPS\b/g, "score"));
const codeText = t => String(t ?? "").replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g, m => human(m));
const badge = s => `<span class="badge s-${esc(s)}" title="${esc(s)}">${esc(human(s))}</span>`;
const bytes = n => typeof n !== "number" ? "" : esc(n > 1e6 ? (n/1e6).toFixed(1) + " MB" : n > 1e3 ? (n/1e3).toFixed(1) + " kB" : n + " B");
const arr = a => Array.isArray(a) ? a : [];

// A server that accepts the connection but never answers (suspended, blocked) would otherwise leave
// the request, and the live-status poll waiting on it, pending forever.
const API_TIMEOUT_MS = 15000;
async function api(path) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), API_TIMEOUT_MS);
  try {
    const r = await fetch(path, {cache: "no-store", credentials: "same-origin", signal: ctl.signal});
    let j; try { j = await r.json(); } catch (e) { return {__error: "HTTP " + r.status + " (response was not JSON)"}; }
    if (!r.ok) return {__error: (j && j.error) || ("HTTP " + r.status)};
    return j;
  } catch (e) {
    return {__error: e && e.name === "AbortError" ? "the local server did not answer within " + API_TIMEOUT_MS / 1000 + " s"
      : "the local server did not respond — is ui/server.py still running?"};
  } finally { clearTimeout(t); }
}
const errBox = e => `<div class="panel" role="alert"><h2 class="bad">Could not load</h2><div>${esc(e)}</div></div>`;

function table(rows, cols, labels) {
  rows = arr(rows);
  if (!rows.length) return '<div class="empty">No rows.</div>';
  cols = cols || Object.keys(rows[0]);
  return `<div class="tablewrap"><table><thead><tr>${cols.map((c,i) => `<th scope="col">${esc(labels ? labels[i] : c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${fmt(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function fileRow(f) {
  if (!f) return "";
  if (!f.exists) return `<tr><td><code>${esc(f.path)}</code></td><td class="bad">missing</td><td></td><td></td></tr>`;
  return `<tr><td><code>${esc(f.path)}</code></td><td>${esc(f.modified)}</td><td>${bytes(f.size_bytes)}</td>
    <td>${f.records != null ? esc(f.records) + " records" : ""}</td></tr>`;
}
function files(list) {
  list = arr(list);
  if (!list.length) return '<span class="muted">none</span>';
  return `<div class="tablewrap"><table><thead><tr><th scope="col">file</th><th scope="col">modified (UTC)</th><th scope="col">size</th><th scope="col">records</th></tr></thead>
    <tbody>${list.map(fileRow).join("")}</tbody></table></div>`;
}
function kv(rec) {
  if (!rec || typeof rec !== "object") return "";
  return `<div class="tablewrap"><table>${Object.entries(rec).map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${fmt(v)}</td></tr>`).join("")}</table></div>`;
}

// ---------- charts without inline styles (CSP): native <meter> bars ----------
const bar = (v, label) => typeof v === "number"
  ? `<meter min="0" max="1" value="${esc(v)}" title="${esc(label || "")} ${esc(v.toFixed(3))}"></meter>`
  : '<span class="muted small">not measured</span>';
const pct = (lo, hi) => (typeof lo === "number" && typeof hi === "number") ? `[${lo.toFixed(3)}, ${hi.toFixed(3)}]` : "—";
const sigVerdict = (lo, hi) => (typeof lo !== "number" || typeof hi !== "number") ? ""
  : (lo <= 0 && hi >= 0 ? '<span class="warn">CI includes 0 — not significant</span>' : '<span class="ok">CI excludes 0</span>');

// ---------- source links: built only from identifiers that match a strict pattern; opened on click only ----------
const LINKS = {
  nct: [/^NCT\d{8}$/, id => "https://clinicaltrials.gov/study/" + id],
  pmid: [/^\d{6,9}$/, id => "https://pubmed.ncbi.nlm.nih.gov/" + id + "/"],
  setid: [/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/, id => "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=" + id],
  ensembl: [/^ENSG\d{11}$/, id => "https://www.ensembl.org/id/" + id],
  chembl: [/^CHEMBL\d+$/, id => "https://www.ebi.ac.uk/chembl/compound_report_card/" + id + "/"],
  reactome: [/^R-HSA-\d+$/, id => "https://reactome.org/content/detail/" + id],
};
function extLink(kind, id, text) {
  const L = LINKS[kind]; id = String(id ?? "");
  if (!L || !L[0].test(id)) return esc(text || id || "—");
  return `<a href="${esc(L[1](id))}" target="_blank" rel="noopener noreferrer" title="Opens the public record in a new tab">${esc(text || id)}</a>`;
}
// PMIDs / NCT IDs inside free text (e.g. "PMID 27062307") become links; everything else stays escaped text.
const linkify = s => esc(codeText(s)).replace(/PMID\s*(\d{6,9})/g, (m, id) => extLink("pmid", id, m)).replace(/\b(NCT\d{8})\b/g, (m, id) => extLink("nct", id));

// Provenance (files, versions, agent identifiers) kept one click away from researcher-facing text.
const provBox = inner => `<details class="prov"><summary>Source and provenance</summary>${inner}</details>`;
// ---------- 10h evidence states ----------
const STATE_CLASS = {MEASURED: "ok", ASSESSED: "ok", MEASURED_ZERO: "zero", PARTIAL: "warn", INSUFFICIENT: "gray",
  ABSENT_AT_SOURCE: "gray", NOT_COMPUTED: "gray", NOT_RETRIEVED: "gray", RETRIEVAL_FAILED: "bad"};
const STATE_SHORT = {MEASURED: "measured", ASSESSED: "assessed", MEASURED_ZERO: "measured: zero", PARTIAL: "partial",
  INSUFFICIENT: "insufficient", ABSENT_AT_SOURCE: "absent at source", NOT_COMPUTED: "not computed",
  NOT_RETRIEVED: "not retrieved", RETRIEVAL_FAILED: "retrieval failed"};
const stateBadge = (s, help) => `<span class="badge st-${esc(STATE_CLASS[s] || "gray")}" title="${esc(help || "")}">${esc(STATE_SHORT[s] || s || "—")}</span>`;
const STATE_LEGEND = `<div class="legend small">${stateBadge("MEASURED")} value from retrieved evidence ·
  ${stateBadge("MEASURED_ZERO")} a real measurement of zero / no signal (a finding, not a gap) ·
  ${stateBadge("PARTIAL")} incomplete input · ${stateBadge("ABSENT_AT_SOURCE")} source queried, no record ·
  ${stateBadge("NOT_RETRIEVED")} never retrieved · ${stateBadge("NOT_COMPUTED")} stage produced no value ·
  ${stateBadge("RETRIEVAL_FAILED")} recorded failure · ${stateBadge("INSUFFICIENT")} too little to conclude</div>`;

function completenessPanel(cp) {
  cp = cp || {};
  const head = `<section class="panel"><h2>What is measured and what is missing</h2>
    ${cp.status ? "" : arr(cp.stale_inputs).length ? `<div class="small warn">Inputs have changed since this assessment was produced; it may be out of date.</div>` : ""}
    ${provBox(`Completeness &amp; Gap agent (10h) · <code>${esc(cp.source)}</code>${cp.agent_version ? " · " + esc(cp.agent_version) : ""} · diagnostic, not part of the score${arr(cp.stale_inputs).length ? ` · changed inputs: ${cp.stale_inputs.map(esc).join(", ")}` : " · inputs unchanged since it ran"}`)}`;
  if (cp.status) return head + `<div class="empty">${esc(cp.status)}</div></section>`;
  const D = cp.domains || {}, meta = cp.domains_meta || {}, SM = cp.state_meaning || {};
  const order = ["clinical", "literature", "safety", "molecular", "proximity", "trial_outcomes", "trial_roles", "adverse_events",
    "conflict_context", "reproducibility", "evidence_independence", "literature_credibility"];
  return head + STATE_LEGEND + `<div class="tablewrap"><table><thead><tr><th scope="col">evidence</th><th scope="col">state</th><th scope="col">what it means here</th><th scope="col">effect on the score</th></tr></thead><tbody>
    ${order.filter(k => D[k]).map(k => `<tr><td>${esc(plainText((meta[k] || {}).label || k))}<div class="small muted">${esc(plainText((meta[k] || {}).kind || ""))}</div></td>
      <td>${stateBadge(D[k].state, SM[D[k].state])}</td><td class="small">${linkify(plainText(D[k].detail))}</td>
      <td class="small">${esc(plainText(D[k].vps_treatment || ((meta[k] || {}).kind === "VPS dimension" ? "" : "not used by the score")))}</td></tr>`).join("")}
    </tbody></table></div>
    ${arr(cp.vps_dimensions_imputed_not_flagged).length ? `<div class="small warn">Median-imputed without a missing flag in stage 06: ${cp.vps_dimensions_imputed_not_flagged.map(esc).join(", ")}.</div>` : ""}
    <h3>Gaps and what would close them (${arr(cp.gaps).length})</h3>
    ${arr(cp.gaps).length ? `<ul class="small">${cp.gaps.map(g => `<li>${stateBadge(g.state)} <strong>${esc(plainText((meta[g.domain] || {}).label || g.domain))}</strong> <span class="muted">(${esc(human(g.severity))} priority)</span> — needed: ${esc(plainText(g.needed_to_close))}</li>`).join("")}</ul>` : '<div class="empty">No gaps recorded.</div>'}
    <h3>Open research questions</h3><ul class="small">${arr(cp.open_questions).map(q => `<li>${esc(plainText(q))}</li>`).join("")}</ul></section>`;
}

function summaryPanel(s, P) {
  if (!s) return "";
  const claim = c => `<li><strong>${linkify(c.source_id)}</strong> <span class="muted">${esc(c.source_date || "date n/a")} · ${esc(c.domain)}${c.temporal ? " · " + esc(human(c.temporal)) : ""}</span><div>${linkify(c.excerpt)}</div>${c.caveat ? `<div class="muted">Caveat: ${esc(c.caveat)}</div>` : ""}</li>`;
  const list = (xs, none) => arr(xs).length ? `<ul class="small claims">${xs.map(claim).join("")}</ul>` : `<div class="small muted">${esc(none)}</div>`;
  return `<section class="panel summary"><h2>Evidence for and against</h2><p>${esc(plainText(s.text))}</p>
    <div class="cols3">
      <div><h3 class="ok">Supporting findings</h3>${list(s.supporting, "None recorded in persisted sources.")}</div>
      <div><h3 class="warn">Null or opposing findings</h3>${list(s.null_or_opposing, "None recorded in persisted sources.")}</div>
      <div><h3 class="bad">Safety concerns</h3>${arr(s.safety_concerns).length ? `<ul class="small claims">${s.safety_concerns.map(c => `<li>${linkify(c.text)} <div class="muted" title="${esc(c.source)}">FDA label${c.label_date ? " · " + esc(c.label_date) : ""}${c.label_set_id ? " · " + extLink("setid", c.label_set_id, "open on DailyMed") : ""}</div></li>`).join("")}</ul>` : '<div class="small muted">No boxed warning or listed serious term in the FDA label.</div>'}</div>
    </div><div class="small muted">${esc(s.note)}</div></section>`;
}

// ---------- agent run header shared by 10c/10f/10g panels ----------
function agentHead(title, b) {
  b = b || {};
  const stale = arr(b.stale_inputs).length;
  return `<section class="panel"><h2>${title}</h2>
    ${stale ? '<div class="small warn">Inputs have changed since this assessment was produced; it may be out of date.</div>' : ""}
    ${provBox(`<code>${esc(b.source)}</code>${b.agent_version ? " · " + esc(b.agent_version) : ""}${b.generated_utc ? " · generated " + esc(b.generated_utc) : ""}${b.run_status ? " · " + esc(human(b.run_status)) : ""}${stale ? ` · changed inputs: ${b.stale_inputs.map(esc).join(", ")}` : ""}`)}`;
}
const notCovered = b => (b || {}).status ? `<div class="empty" role="status">${esc(b.status)}</div></section>` : "";

function clinicalPanel(b) {
  const head = agentHead("Clinical trials before 2021: status, results and the drug's role", b);
  if ((b || {}).status) return head + notCovered(b);
  const links = Object.fromEntries(arr(b.links).map(l => [l.nct_id, l]));
  const rows = arr(b.trial_records).filter(Boolean);
  const awaiting = new Set(arr((reviewCache || {}).rows).filter(r => r.compound === b.compound && String(r.status).startsWith("UNRESOLVED")).map(r => r.nct_id));
  const role = l => l.role_manual ? `${esc(human(l.role_manual.category))} <span class="small ok">(human-reviewed)</span>`
    : `${esc(human(l.role_auto))} <span class="small ${awaiting.has(l.nct_id) ? "warn" : "muted"}">(${awaiting.has(l.nct_id) ? "automatic reading — awaiting human review" : "automatic reading"})</span>`;
  const res = t => { const r = t.results || {};
    if (r.state !== "RESULTS_POSTED") return `<span class="muted small">${esc((b.state_meaning || {})[r.state] || r.state)}</span>`;
    return `<div class="small">posted ${esc(r.results_first_posted)} ${r.temporal === "POST_CUTOFF" ? '<span class="warn">(after 2021 cutoff)</span>' : ""}</div>
      ${arr(r.primary_analyses).slice(0, 3).map(a => `<div class="small">${esc(a.outcome)}: ${a.p_value != null ? "p = " + esc(a.p_value) : '<span class="muted">' + esc(a.note || "no p-value posted") + "</span>"}${a.estimate ? ` · ${esc(a.estimate_type)} ${esc(a.estimate)}` : ""}${a.ci && a.ci[0] ? ` [${esc(a.ci[0])}, ${esc(a.ci[1])}]` : ""}</div>`).join("")}`; };
  const sc = b.status_counts || {};
  return head + `<div class="small">${esc(b.n_trials)} pre-2021 trial(s): ${Object.entries(sc).filter(([, n]) => n).map(([k, n]) => `${esc(k)} ${esc(n)}`).join(" · ")} · results posted for ${esc(b.n_results_posted)} · drug tested in ${esc(b.n_links_drug_tested)} · trial-matching outcomes: ${Object.entries(b.matching_audit_outcomes || {}).map(([k, n]) => `${esc(human(k))} ${esc(n)}`).join(", ") || "—"}</div>
    <div class="tablewrap"><table><thead><tr><th scope="col">trial</th><th scope="col">phase · status</th><th scope="col">design</th><th scope="col">role of this drug</th><th scope="col">posted results (verbatim)</th></tr></thead><tbody>
    ${rows.map(t => `<tr><td>${extLink("nct", t.nct_id)}<div class="small muted">${esc(t.title || "")}</div></td>
      <td class="small">${esc(arr(t.phases).map(human).join("/") || "no phase")} · ${esc(human(t.overall_status || "—"))}${t.why_stopped ? `<div class="warn">stopped: ${esc(t.why_stopped)}</div>` : ""}</td>
      <td class="small">${esc(human(t.allocation || ""))} ${esc(human(t.masking || ""))} · n=${fmt(t.enrollment)} · ${esc(human(t.primary_purpose || ""))}</td>
      <td class="small">${links[t.nct_id] ? role(links[t.nct_id]) : "—"}</td><td>${res(t)}</td></tr>`).join("")}</tbody></table></div>
    <div class="small muted">${esc(b.interpretation)} Trial roles are shown for review; they do not change the score until the project owner decides how to apply them.</div></section>`;
}

function safetyPanel(b) {
  const head = agentHead("Safety: FDA label and spontaneous adverse-event reports", b);
  if ((b || {}).status) return head + notCovered(b);
  const L = b.label || {}, F = b.faers || {}, SM = b.state_meaning || {};
  return head + `<div class="cols"><div><h3>FDA label ${stateBadgeSrc(L.state)}</h3>
      ${L.state === "RETRIEVED" ? `<div class="small">${extLink("setid", L.label_set_id, "DailyMed label")} · effective ${esc(L.effective_time)} · boxed warning: <strong>${L.boxed_warning ? "yes" : "no"}</strong> · serious terms in warnings: ${fmt(L.serious_term_count)}</div>
        ${L.boxed_warning_excerpt ? `<blockquote class="small">${esc(L.boxed_warning_excerpt)}…</blockquote>` : ""}<div class="small muted">${esc(L.detail)}${L.temporal ? ` · took effect ${L.temporal === "POST_CUTOFF" ? "after" : "before"} the 2020-12-31 cutoff` : ""}</div>
        ${atCutoff(L.at_cutoff)}`
        : `<div class="small">${esc(L.detail || SM[L.state] || "")}</div>`}</div>
    <div><h3>FAERS spontaneous reports ${stateBadgeSrc(F.state)}</h3>
      ${F.state === "RETRIEVED" ? `<div class="small">${fmt(F.total_reports)} reports · ${fmt(F.serious_reports)} serious · ${fmt(F.death_reports)} with death as an outcome · ${fmt(F.reports_received_by_2020)} received by 2020 · retrieved ${esc(F.retrieved_utc)}</div>
        <div class="small">Most reported reactions: ${arr(F.top_reactions).map(r => `${esc(r.term)} (${esc(r.count)})`).join(", ") || "—"}</div>
        ${arr(F.failed_queries).length ? `<div class="small warn">Failed queries: ${F.failed_queries.map(esc).join(", ")}</div>` : ""}`
        : `<div class="small">${esc(F.detail || SM[F.state] || "")}</div>`}
      <div class="small muted">Reports are not incidence: no denominator, voluntary and biased reporting, no causality. Not part of the score.</div></div></div></section>`;
}
function atCutoff(a) {
  if (!a) return "";
  if (a.state === "SCORED") return `<div class="small">Label at the cutoff (DailyMed v${esc(a.version)}, ${esc(a.version_date)}): boxed warning <strong>${a.boxed_warning ? "yes" : "no"}</strong> · serious terms ${fmt(a.serious_term_count)}${a.changed_since_cutoff ? ' · <span class="warn">changed since the cutoff</span>' : " · unchanged since the cutoff"}</div>`;
  const T = {UNKNOWN: "Label at the cutoff: unknown — this label's history starts after 2020; an older label under another set ID is not ruled out.",
    NO_RECORD: "Label at the cutoff: no current label to trace.", FAILED: "Label at the cutoff: retrieval failed (recorded).",
    NOT_RETRIEVED: "Label at the cutoff: not retrieved (stage 05h not run)."};
  return `<div class="small muted">${esc(T[a.state] || a.detail || "")}</div>`;
}
const stateBadgeSrc = s => `<span class="badge st-${{RETRIEVED: "ok", NO_RECORD: "gray", FAILED: "bad", NOT_RETRIEVED: "gray"}[s] || "gray"}">${esc({RETRIEVED: "retrieved", NO_RECORD: "no record at source", FAILED: "retrieval failed", NOT_RETRIEVED: "not retrieved"}[s] || s || "—")}</span>`;

function independencePanel(b) {
  const head = agentHead("Is the evidence independent?", b);
  if ((b || {}).status) return head + notCovered(b);
  const names = {D1_shared_trial_across_compounds: "Trial also credited to other candidates", D2_same_study_in_two_dimensions: "Same study counted as a trial and as a paper",
    D3_duplicated_or_pooled_claims: "Outcome claims from the same or pooled data", D4_molecular_datatype_reuse: "Molecular score re-uses clinical/literature data",
    D5_duplicate_publication_in_sample: "Same publication counted twice in the literature sample"};
  const cls = {DEPENDENCE_FOUND: "warn", NONE_FOUND: "ok", NOT_ASSESSABLE: "gray"};
  return head + `<div class="tablewrap"><table><thead><tr><th scope="col">check</th><th scope="col">result</th><th scope="col">detail</th></tr></thead><tbody>
    ${Object.entries(b.checks || {}).map(([k, c]) => `<tr><td>${esc(names[k] || k)}</td><td><span class="badge st-${cls[c.state] || "gray"}" title="${esc((b.state_meaning || {})[c.state] || "")}">${esc(String(c.state).replace(/_/g, " ").toLowerCase())}</span></td>
      <td class="small">${esc(plainText(c.detail))}${arr(c.shared_trials).length ? `<div>${c.shared_trials.map(t => `${extLink("nct", t.nct_id)} also: ${t.also_credited_to.map(esc).join(", ")} <span class="muted">(${esc(t.role_here)})</span>`).join("<br>")}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>
    <div class="small muted">"None found" means checked and nothing found, not proof of independence. Nothing is de-duplicated in the score.</div></section>`;
}

// 10d output: claims and pairwise comparisons, both sides with their sources.
function conflictPanel(cc) {
  cc = cc || {};
  const head = `<section class="panel"><h2>Conflicting evidence ${badge(cc.status || "unavailable")}</h2>
    <div class="small muted">Disagreements between sources are classified (different population, endpoint, significance or evidence type), never averaged into the score.</div>
    ${provBox(`Conflict &amp; Context agent (10d) · <code>${esc(cc.source)}</code> · diagnostic, not part of the score`)}`;
  if (!cc.claims) return head + `<div class="empty">${esc(cc.status || "No 10d output.")}</div></section>`;
  const side = s => `<div><strong>${esc(s.source_id)}</strong> <span class="muted">${esc(s.source_date || "date n/a")}</span> · ${badge(s.direction)} · ${esc(s.domain)}${s.endpoint_measure ? " · " + esc(s.endpoint_measure) : ""}${s.population ? " · " + esc(s.population) : ""}<div class="small muted">${esc(s.excerpt)}</div></div>`;
  const comps = arr(cc.comparisons);
  const cov = cc.coverage || {};
  return head + `<div class="small">${esc(cc.n_claims)} claims (${esc(cc.n_directional_claims)} directional) · coverage: ${Object.entries(cov).map(([k, v]) => `<span class="chip">${esc(k.replace(/_/g, " "))}: ${esc(v)}</span>`).join("")}</div>
    ${comps.length ? `<h3>Comparisons (${comps.length})</h3><div class="tablewrap"><table><thead><tr><th scope="col">classification</th><th scope="col">side A</th><th scope="col">side B</th><th scope="col">why</th></tr></thead><tbody>
      ${comps.map(c => `<tr><td>${badge(c.classification)}${arr(c.flags).map(f => `<div class="chip">${esc(f)}</div>`).join("")}</td><td>${side(c.side_a)}</td><td>${side(c.side_b)}</td><td class="small">${esc(c.rationale)}${arr(c.differing_axes).length ? `<div>differs: ${c.differing_axes.map(esc).join(", ")}</div>` : ""}</td></tr>`).join("")}
      </tbody></table></div>` : '<div class="empty">No pair of directional claims from different sources disagrees (or fewer than two directional sources exist).</div>'}
    <details><summary>All ${arr(cc.claims).length} claims (with provenance)</summary>${table(arr(cc.claims).map(c => ({direction: c.direction, domain: c.domain, source: c.source_id, date: c.source_date, temporal: c.temporal, endpoint: c.endpoint_measure || c.endpoint_domain, population: c.population, excerpt: c.excerpt, provenance: c.provenance, note: c.note || c.caveat || c.label_strength})))}</details>
    ${arr(cc.insufficient).length ? `<div class="small warn">${cc.insufficient.length} item(s) recorded as insufficient (e.g. stopped trials with no retrieved reason) — not counted as evidence either way.</div>` : ""}
  </section>`;
}

// 10e output: finding-level replication and paper-sample structure.
function reproPanel(rp) {
  rp = rp || {};
  const head = `<section class="panel"><h2>Has the finding been replicated?</h2>
    <div class="small muted">Independence between studies is at best "plausible": study populations and datasets are not recorded.</div>
    ${provBox(`Reproducibility agent (10e) · <code>${esc(rp.source)}</code> · diagnostic, not part of the score`)}`;
  if (rp.status) return head + `<div class="empty">${esc(rp.status)}</div></section>`;
  const F = arr(rp.findings), S = rp.publication_structure, T = arr(rp.shared_trials), M = rp.finding_status_meaning || {};
  return head + (F.length ? `<div class="tablewrap"><table><thead><tr><th scope="col">finding</th><th scope="col">status</th><th scope="col">independence</th><th scope="col">primary / secondary records</th><th scope="col">clusters by direction</th></tr></thead><tbody>
      ${F.map(f => `<tr><td>${esc(f.finding)}</td><td>${badge(f.status)}<div class="small muted">${esc(M[f.status] || "")}</div></td><td>${esc(f.cluster_independence || "—")}</td><td>${esc(f.n_primary)} / ${esc(f.n_secondary)}</td><td class="small">${Object.entries(f.directions_by_cluster || {}).map(([d, g]) => `${esc(d)}: ${g.map(c => c.map(p => "PMID " + p).join("+")).map(esc).join(" · ")}`).join("<br>") || "—"}</td></tr>`).join("")}</tbody></table></div>`
    : '<div class="empty">Not assessed for this compound: replication is assessed only for curated outcome findings with PubMed IDs, which exist for the case-study compounds.</div>')
    + (S ? `<h3>Paper sample structure</h3><div class="small">${esc(S.n_papers_in_graph)} papers · designs ${fmt(S.designs)} · ${esc(S.n_primary)} primary records in ${esc(S.n_independent_primary_clusters)} cluster(s) · stage-04 components: ${esc(S.n_10g_components)} · ${esc(S.finding_replication)}</div>` : "")
    + (T.length ? `<h3>Trials shared with other compounds</h3>${table(T.map(t => ({trial: t.nct_id, file: t.file, compounds: t.compounds.join(", ")})))}<div class="small muted">A shared trial raises clinical maturity for every compound it names; it is one study, not independent evidence.</div>` : "")
    + "</section>";
}

// What each dimension's value means: measured, measured zero, not measured, or not retrieved.
function evidenceStates(d) {
  const D = d.dimensions || {}, P = d.pool || {}, miss = arr(P.dimensions_missing);
  const raw = {proximity: "proximity_z", clinical: "max_phase_rank", literature: "effective_independent_count",
               safety: "serious_term_count", molecular: "molecular_plausibility_score"};
  const rows = Object.entries(raw).map(([k, col]) => {
    const blk = D[k] || {}, v = (blk.in_vps || {})[col];
    let state;
    if (blk.status && blk.status.startsWith("artefact")) state = "artefact missing (stage not run or retrieval failed)";
    else if (miss.includes(k)) state = "NOT MEASURED — missing evidence, shown at neutral rank 0.5 (not 'safe', not 'negative')";
    else if (blk.status === "no record for this compound") state = "no record (not retrieved, or retrieval failed — the artefact cannot tell)";
    else if (v === 0) state = "measured ZERO (a real measurement)";
    else if (v === null || v === undefined) state = "no value";
    else state = "measured";
    return {dimension: k, raw_value: v, rank: (blk.in_vps || {})["r_" + k], state};
  });
  return `<h3>Evidence state per dimension</h3><div class="tablewrap"><table><thead><tr><th scope="col">dimension</th><th scope="col">raw</th><th scope="col">rank (0–1)</th><th scope="col">state</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td>${esc(r.dimension)}</td><td>${fmt(r.raw_value)}</td><td>${bar(r.rank, r.dimension)} ${fmt(r.rank)}</td><td class="small">${esc(r.state)}</td></tr>`).join("")}</tbody></table></div>
    <div class="small muted">Null results and harms are not a score dimension; they are listed under "Null or opposing findings" and "Conflicting evidence" with their sources.</div>`;
}

// ---------- tiny markdown renderer (escapes first; no raw HTML passthrough) ----------
const DOC_KEYS = {"README.md": "README", "TECHNICAL_DEBT.md": "TECHNICAL_DEBT", "CHANGES.md": "CHANGES",
  "ERRORS_AND_BLOCKERS.md": "ERRORS_AND_BLOCKERS", "CASE_STUDIES.md": "CASE_STUDIES",
  "INTERVENTION_MATCHING.md": "INTERVENTION_MATCHING", "MOLECULAR_AGENT.md": "MOLECULAR_AGENT", "REFERENCES.md": "REFERENCES"};
function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  // Only http(s) links become anchors; the URL was already HTML-escaped above.
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  // Links to another dashboard doc stay inside the dashboard; anything else is shown, not linked.
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, text, href) => {
    const key = DOC_KEYS[href.split("#")[0].split("/").pop()];
    return key ? `<a href="#cases/${key}">${text}</a>` : `${text} <span class="muted small">(${href})</span>`;
  });
  return s;
}
function md(text) {
  const lines = String(text || "").split("\n"); let out = [], i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) { const buf = []; i++; while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]); i++;
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`); continue; }
    const h = l.match(/^(#{1,4})\s+(.*)$/); if (h) { const n = Math.min(h[1].length + 1, 5); out.push(`<h${n}>${inline(h[2])}</h${n}>`); i++; continue; }
    if (/^\|/.test(l)) { const rows = []; while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const body = rows.filter((r, k) => !(k === 1 && /^\|[\s:\-|]+\|?$/.test(r)));
      out.push(`<div class="tablewrap"><table>${body.map((r, k) => `<tr>${cells(r).map(c => k === 0 ? `<th scope="col">${inline(c)}</th>` : `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</table></div>`); continue; }
    if (/^>/.test(l)) { const buf = []; while (i < lines.length && /^>/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${buf.map(inline).join("<br>")}</blockquote>`); continue; }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) { const buf = []; while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""); while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) item += " " + lines[i++].trim();
        buf.push(`<li>${inline(item)}</li>`); }
      out.push(`<ul>${buf.join("")}</ul>`); continue; }
    if (/^---+\s*$/.test(l)) { out.push("<hr>"); i++; continue; }
    if (!l.trim()) { i++; continue; }
    const buf = [l]; i++; while (i < lines.length && lines[i].trim() && !/^(#|\||>|```|\s*([-*]|\d+\.)\s)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join(" "))}</p>`);
  }
  return out.join("\n");
}

// ---------- views: each returns {html, after?}; after() runs once the HTML is in the DOM ----------
function riskPanel(R) {
  if (!R || R.__error) return errBox((R || {}).__error || "risks unavailable");
  return `<section class="panel"><h2>Unresolved high-severity risks</h2>
    <div class="prov">From <code>${esc(R.source)}</code> (HIGH / BLOCKER entries without a resolution marker).</div>
    ${arr(R.open_high).length ? `<ul class="small">${R.open_high.map(i => `<li><strong>${esc(i.id)}</strong> ${badge(i.severity)} ${esc(i.title)} <span class="muted">${esc(i.status)}</span></li>`).join("")}</ul>` : '<div class="empty">None recorded.</div>'}</section>`;
}
// Researcher landing page: what is known, how current and reliable it is, what needs attention, what to do next.
const runDate = id => { const m = /(\d{4})(\d{2})(\d{2})T/.exec(String(id || "")); return m ? `${m[1]}-${m[2]}-${m[3]}` : null; };
const STATE_HEADLINE = {UNKNOWN: "Freshness could not be verified", RUNNING: "A run is in progress", FAILED: "Last run failed; previous results retained",
  STALE: "Inputs changed — rerun needed", INCOMPLETE: "Some stages have never run", VERIFIED_WITH_GAPS: "Current against recorded inputs, with unverifiable inputs",
  CURRENT: "Current against recorded inputs"};
async function viewOverview() {
  const [o, ev, L, RS] = await Promise.all([api("/api/overview"), api("/api/evaluation"), api("/api/live"), api("/api/result_set")]);
  if (o.__error || o.status) return errBox(o.__error || o.status);
  if (!rankingCache || rankingCache.__error) rankingCache = await api("/api/ranking");
  const rows = arr((rankingCache || {}).rows), C = o.cohort || {}, r3 = x => typeof x === "number" ? x.toFixed(3) : "—";
  const prim = arr(ev.primary), p5 = prim.find(p => /5d/.test(p.model)) || {}, pd = ev.paired_5d_vs_4d || {};
  const SC = (L && L.science) || {}, F = (L && L.freshness) || {}, ov = (L && L.overall) || {}, srcs = arr(L && L.sources);
  const approvedOn = runDate(SC.approved_run_id);
  const noDate = srcs.filter(x => !x.retrieved_utc).map(x => x.source);
  const dims = ["clinical", "literature", "proximity", "safety", "molecular"], DN = {proximity: "Network proximity", clinical: "Clinical maturity", literature: "Literature independence", safety: "Safety (FDA label)", molecular: "Molecular plausibility"};
  const measured = d => rows.filter(r => !String(r.dimensions_missing || "").split("|").includes(d)).length;
  const imputed = d => rows.filter(r => String(r.dimensions_imputed || "").split("|").includes(d)).length;
  const status = (ok, text) => `<span class="sym ${ok === true ? "ok" : ok === false ? "bad" : "warn"}" aria-hidden="true">${ok === true ? "✓" : ok === false ? "✕" : "!"}</span> ${text}`;
  const stateOk = ov.state === "CURRENT" ? true : ["FAILED", "UNKNOWN"].includes(ov.state) ? false : null;
  const top = rows.filter(r => r.VPS_equal_5d != null).slice(0, 10);
  return `<section class="panel intro"><h2>What you are looking at</h2>
      <p>EviRep ranks the <strong>${fmt(C.compounds)} drugs that had already been tested in Parkinson's disease before 2021</strong> by how much independent clinical, literature, safety, molecular and network evidence exists for them. It then checks, retrospectively, whether higher-ranked drugs were more often taken into new Parkinson's trials after 2020.</p>
      <p class="small"><strong>A high rank is a signal for further research, not evidence that a drug works or is safe.</strong> The score is a rank, not a probability.</p>
      <div class="small muted">Approved result set: 5-dimension equal-weight score${approvedOn ? `, recorded ${esc(approvedOn)}` : ""} · independent recomputation ${SC.independent_recomputation === true ? "matches" : SC.independent_recomputation === false ? '<span class="bad">does not match</span>' : "not recorded"}.</div></section>
    <div class="kpis">
      <div class="panel kpi"><div class="kv">${fmt(C.compounds)}</div><div class="small muted">candidate drugs evaluated</div></div>
      <div class="panel kpi"><div class="kv">${fmt(C.positives)} / ${fmt(C.negatives)}</div><div class="small muted">with / without a new Parkinson's trial after 2020</div></div>
      <div class="panel kpi"><div class="kv">${r3(p5.auroc)}</div><div class="small muted">AUROC (95% CI ${r3((p5.auroc_ci95 || [])[0])}–${r3((p5.auroc_ci95 || [])[1])}); 0.5 = chance</div></div>
      <div class="panel kpi"><div class="kv">${fmt(SC.reviews_awaiting)}</div><div class="small muted">trial links awaiting a human decision</div></div>
    </div>
    <section class="panel"><h2>How current and reliable is it?</h2>
      <ul class="plain checks">
        <li>${status(stateOk, `<strong>Results:</strong> ${esc(STATE_HEADLINE[ov.state] || "Run state unavailable")}.`)}${ov.state === "VERIFIED_WITH_GAPS" ? ` <span class="small">${arr(F.untracked_inputs).map(u => `The ${esc(plainText(u.name || u.stage))} reads an input that was not fingerprinted when it last ran, so a change to it would not be detected.`).join(" ")}</span>` : ""}</li>
        <li>${status(F.last_success_utc ? true : null, `<strong>Last successful run:</strong> ${F.last_success_utc ? esc(String(F.last_success_utc).slice(0, 16).replace("T", " ")) + " UTC" : "not recorded"}.`)}</li>
        <li>${status(noDate.length ? null : true, `<strong>Source data:</strong> ${srcs.length - noDate.length} of ${srcs.length} sources have a recorded retrieval date${noDate.length ? `; not recorded for ${noDate.map(esc).join(", ")}` : ""}.`)}</li>
        <li>${status(null, `<strong>Scientific validation:</strong> retrospective association with continued clinical investigation (not efficacy); literature, safety and molecular evidence are current snapshots rather than data frozen at the 2020 cutoff, so the evaluation is not leakage-free. ${arr(SC.open_decisions).length} methodological decisions are open with the project owner.`)}</li>
      </ul>
      <p class="small"><a href="#run">Run details</a> · <a href="#validation">Validation details</a></p></section>
    <div class="grid2">
      <section class="panel"><h2>Strongest research signals</h2>
        ${chartBars(top.map(r => ({label: `${r.rank}. ${r.compound}`, value: r.VPS_equal_5d, text: fmtN(r.VPS_equal_5d), key: r.compound, cls: r.label === 1 ? "pos" : "",
          mark: (r.label === 1 ? "● " : "") + (r.dimensions_missing || r.dimensions_imputed ? "†" : ""),
          note: [r.label === 1 ? "entered a new Parkinson's trial after 2020" : "no new Parkinson's trial after 2020 found", r.dimensions_missing ? "not measured: " + r.dimensions_missing.split("|").join(", ") : "", r.dimensions_imputed ? "imputed: " + r.dimensions_imputed : ""].filter(Boolean).join("; ")})),
          {title: "Top 10 candidates by approved score", max: 1, left: 170, xLabel: "score (mean of five percentile ranks, 0–1)", caption: "● entered a new Parkinson's trial after 2020 (the evaluation outcome, not efficacy). † a dimension was not measured or was median-imputed. Select a bar to open the candidate."})}
        <p class="small"><a href="#drugs">All ${esc(rows.length)} candidates</a></p></section>
      <section class="panel"><h2>Evidence coverage</h2>
        ${chartBars(dims.map(d => ({label: DN[d], value: measured(d) - imputed(d), text: `${measured(d) - imputed(d)} of ${rows.length}`, note: (rows.length - measured(d) ? `${rows.length - measured(d)} not measured (neutral rank)` : "") + (imputed(d) ? `${imputed(d)} median-imputed` : "")})),
          {title: "Candidates with a measured value, per evidence dimension", max: rows.length || 90, left: 170, xLabel: `candidates (of ${rows.length})`, caption: "Not measured = no FDA label (safety) or no known drug target (molecular); these get a neutral rank, which is not a negative finding." + (dims.some(imputed) ? " Median-imputed values are counted as not measured here: " + dims.filter(imputed).map(d => `${DN[d]} ${imputed(d)}`).join(", ") + "." : "")})}
        <p class="small"><a href="#evidence">Explore the evidence</a></p></section>
    </div>
    <section class="panel"><h2>What needs attention</h2>
      <ul class="plain checks">
        ${SC.reviews_awaiting ? `<li>${status(null, `<strong>${esc(SC.reviews_awaiting)} trial–drug links need a human decision</strong> on the drug's role in the trial (for example tested drug versus background medication). Until then they keep their automatic reading. <a href="#review">Open the review queue</a>`)}</li>` : ""}
        <li>${status(null, `<strong>Adding the molecular dimension is not shown to improve ranking:</strong> paired AUROC difference ${r3(pd.diff)} (95% CI ${r3((pd.ci95 || [])[0])} to ${r3((pd.ci95 || [])[1])}) includes zero.`)}</li>
        ${arr(SC.open_decisions).map(d => `<li>${status(null, `<strong>${esc(d.title)}</strong> (owner decision): ${esc(d.detail)}`)}</li>`).join("")}
      </ul></section>
    <section class="panel"><h2>What you can do next</h2>
      <div class="actions"><a class="btn" href="#drugs">Explore and filter candidates</a><a class="btn" href="#compare">Compare candidates side by side</a><a class="btn" href="#evidence">Search the evidence</a><a class="btn" href="#validation">Check how the ranking was validated</a></div></section>
    <details class="panel"><summary><strong>Technical details</strong></summary>
      <div class="small">Approved run <code>${esc(SC.approved_run_id || "none")}</code>. ${arr(SC.pending_candidates).map(c => `An unapproved alternative result set exists (${esc(c.label)}, <code>${esc(c.id)}</code>); it is not shown anywhere in the results.`).join(" ")}</div>
      <h3>Approved result set: data contract</h3>${resultSetPanel(RS)}
      <h3>Saved result files</h3>${files(o.artefacts)}</details>`;
}

const STANCE = {supporting: "Supports", null_or_opposing: "Null or opposing", context: "Context, not a finding", outcome_label: "Outcome label (after 2020)",
  safety_concern: "Safety consideration", no_listed_concern: "No listed serious concern", missing: "Missing at source", not_assessed: "Not assessed"};
const BASIS = {automatic: "Automatically extracted", curated: "Curated from a publication", human_reviewed: "Human-reviewed", awaiting_review: "Awaiting human review", hypothesis: "Mechanistic hypothesis"};
const TYPE_NAME = {clinical: "Clinical trial", literature: "Publication", safety: "FDA label", molecular: "Drug target"};
const roleText = r => String(r || "").split(" · ").map(x => /^[A-Z_]+$/.test(x) ? human(x) : x).join(" · ");
async function viewEvidence(arg) {
  const E = await api("/api/evidence"); if (E.__error) return errBox(E.__error);
  const items = arr(E.items), types = Object.keys(E.counts || {});
  const opts = (M, key) => Object.entries(M).filter(([k]) => items.some(i => i[key] === k)).map(([k, l]) => `<option value="${esc(k)}">${esc(l)} (${items.filter(i => i[key] === k).length})</option>`).join("");
  const html = `<section class="panel"><h2>Evidence explorer</h2>
    <p class="small">Every saved evidence item — trial registrations, curated publication findings, FDA labels and drug targets — with its identifier, date, what it says and how it was obtained. Identifiers open the public record in a new tab.</p>
    <details class="small legend-box"><summary>How to read "Stance" and "Basis"</summary><dl class="defs">
      <dt>Supports / Null or opposing</dt><dd>Direction of a curated publication finding. Null and opposing findings are shown, not hidden.</dd>
      <dt>Context, not a finding</dt><dd>A trial registration or drug target. A trial's existence is not evidence that the drug works; a target is a mechanistic hypothesis.</dd>
      <dt>Missing at source</dt><dd>The source was queried and has no record (for example no US FDA label). Missing evidence is not negative evidence.</dd>
      <dt>Automatically extracted</dt><dd>Retrieved and matched by the pipeline without human review.</dd>
      <dt>Human-reviewed / Awaiting human review</dt><dd>A person recorded the drug's role in this trial, or the link is in the review queue. This application never decides it.</dd>
      <dt>Mechanistic hypothesis</dt><dd>A drug–target relationship from ChEMBL; plausibility, not proof of an effect in Parkinson's disease.</dd></dl></details>
    <div class="filters">
      <label class="small">Type <select id="etype"><option value="">all (${esc(items.length)})</option>${types.map(t => `<option value="${esc(t)}">${esc(TYPE_NAME[t] || t)} (${esc(E.counts[t])})</option>`).join("")}</select></label>
      <label class="small">Stance <select id="estance"><option value="">any</option>${opts(STANCE, "stance")}</select></label>
      <label class="small">Basis <select id="ebasis"><option value="">any</option>${opts(BASIS, "basis")}</select></label>
      <label class="small">Compound <input id="ecomp" type="search" placeholder="e.g. Donepezil" value="${esc(arg || "")}"></label>
      <label class="small">Text <input id="etext" type="search" placeholder="identifier, phase, gene, words…"></label>
      <span id="ecount" class="small muted" aria-live="polite"></span>
    </div>
    <div class="tablewrap"><table><thead><tr><th scope="col">type</th><th scope="col">compound</th><th scope="col">identifier</th><th scope="col">date</th><th scope="col">what it is</th><th scope="col">stance</th><th scope="col">basis</th><th scope="col">detail</th><th scope="col" class="srccol" hidden>source file</th></tr></thead><tbody id="ebody"></tbody></table></div>
    <div class="small"><button type="button" class="act ghost" id="emore" hidden>Show 100 more</button> <label><input type="checkbox" id="esrc"> Show source files (technical)</label></div></section>`;
  const after = () => {
    const t = document.getElementById("etype"), c = document.getElementById("ecomp"), x = document.getElementById("etext"), st = document.getElementById("estance"), ba = document.getElementById("ebasis");
    const render = () => {
      const cq = c.value.trim().toLowerCase(), xq = x.value.trim().toLowerCase();
      const hits = items.filter(i => (!t.value || i.type === t.value) && (!st.value || i.stance === st.value) && (!ba.value || i.basis === ba.value)
        && (!cq || String(i.compound).toLowerCase().includes(cq))
        && (!xq || [i.id, i.detail, i.role, i.date].some(v => String(v ?? "").toLowerCase().includes(xq))));
      document.getElementById("ecount").textContent = `${hits.length} items` + (hits.length > evShown ? ` (showing the first ${evShown})` : "");
      const showSrc = document.getElementById("esrc").checked;
      document.querySelectorAll(".srccol").forEach(th => { th.hidden = !showSrc; });
      document.getElementById("emore").hidden = hits.length <= evShown;
      document.getElementById("ebody").innerHTML = hits.slice(0, evShown).map(i => `<tr><td>${esc(TYPE_NAME[i.type] || i.type)}</td><td><a href="${esc(drugHref(i.compound))}">${esc(i.compound)}</a></td>
        <td class="nowrap">${i.id_kind === "none" ? '<span class="muted">none</span>' : extLink(i.id_kind, i.id, i.id_kind === "pmid" ? "PMID " + i.id : i.id_kind === "setid" ? "DailyMed label" : i.id)}${i.chembl_id ? "<br>" + extLink("chembl", i.chembl_id) : ""}</td>
        <td>${fmt(i.date)}</td><td class="small">${esc(roleText(i.role))}</td><td class="small"><span class="stance st-${esc(i.stance)}">${esc(STANCE[i.stance] || i.stance)}</span></td><td class="small"><span class="basis b-${esc(i.basis)}">${esc(BASIS[i.basis] || i.basis)}</span></td><td class="small">${esc(codeText(i.detail))}</td>${showSrc ? `<td class="small"><code>${esc(i.source)}</code></td>` : ""}</tr>`).join("")
        || '<tr><td colspan="9" class="muted">No item matches. Clear a filter to see more.</td></tr>';
    };
    [t, c, x, st, ba].forEach(el => el.addEventListener("input", () => { evShown = 100; render(); }));
    document.getElementById("esrc").addEventListener("change", render);
    document.getElementById("emore").addEventListener("click", () => { evShown += 100; render(); });
    render();
  };
  return {html, after};
}
let evShown = 100;

// Drug -> target -> Parkinson's disease, from the molecular agent's saved record: solid = direct target-disease
// association (leakage-controlled datatypes), dashed = indirect via pathways shared with PD genes.
function chartChain(drug, E) {
  const targets = arr(E.targets).slice(0, 10);
  if (!targets.length) return '<div class="empty">No known drug target, so no mechanistic chain can be drawn. This is unmeasured evidence, not negative evidence.</div>';
  const direct = {}; arr(E.disease_links).forEach(x => { direct[x.gene_symbol] = x.score_allowed_datatypes; });
  const shared = {}; arr(E.pathways).forEach(p => { if (p.in_disease_module) shared[p.gene_symbol] = (shared[p.gene_symbol] || new Set()).add(p.pathway_id); });
  const rowH = 30, H = Math.max(120, targets.length * rowH + 20), W = 680, xd = 10, xt = 210, xp = 400, xpd = 580;
  const cy = H / 2;
  return `<figure class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mechanistic chain for ${esc(drug)}"><title>Mechanistic chain for ${esc(drug)}</title>
    <defs><marker id="arr2" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="arrowhead"/></marker></defs>
    <g class="node st-SUCCESS"><rect x="${xd}" y="${cy - 16}" width="130" height="32" rx="5"/><text x="${xd + 65}" y="${cy + 4}" text-anchor="middle" class="nid">${esc(drug)}</text></g>
    <g class="node st-SUCCESS"><rect x="${xpd}" y="${cy - 16}" width="92" height="32" rx="5"/><text x="${xpd + 46}" y="${cy + 4}" text-anchor="middle" class="nid">Parkinson's</text></g>
    ${targets.map((t, i) => { const y = 10 + i * rowH + rowH / 2, g = t.gene_symbol || t.ensembl_id, d = direct[g], n = shared[g] ? shared[g].size : 0;
      return `<path class="edge" d="M${xd + 130},${cy} C${xd + 170},${cy} ${xt - 40},${y} ${xt - 3},${y}" marker-end="url(#arr2)"/>
        <g class="node"><rect x="${xt}" y="${y - 11}" width="110" height="22" rx="4"/><text x="${xt + 55}" y="${y + 4}" text-anchor="middle">${esc(g)}</text><title>${esc(g)} · ${esc(t.mechanism_of_action || t.action_type || "")}</title></g>
        ${d > 0 ? `<path class="edge direct" d="M${xt + 110},${y} C${xt + 200},${y} ${xpd - 60},${cy} ${xpd - 3},${cy}" marker-end="url(#arr2)"><title>direct association ${fmtN(d)}</title></path><text class="val" x="${xt + 116}" y="${y - 3}">direct ${fmtN(d, 2)}</text>`
          : `<text class="tick" x="${xt + 116}" y="${y + 4}">no direct association</text>`}
        ${n ? `<path class="edge indirect" d="M${xt + 110},${y + 2} C${xp},${y + 2} ${xpd - 80},${cy + 6} ${xpd - 3},${cy + 6}"><title>${n} pathway(s) shared with Parkinson's genes</title></path><text class="tick" x="${xp}" y="${y + 12}">${n} shared pathway${n > 1 ? "s" : ""}</text>` : ""}`; }).join("")}
    </svg><figcaption class="small muted">Solid arrow: direct target–Parkinson's association (Open Targets, outcome-leaking datatypes excluded). Dashed: indirect link through pathways shared with Parkinson's genes. A target link is mechanistic plausibility, not evidence that the drug works.${arr(E.targets).length > 10 ? ` First 10 of ${arr(E.targets).length} targets shown.` : ""}</figcaption>
    ${dataTable("Mechanistic chain for " + drug, ["target", "direct association", "shared PD pathways"], targets.map(t => { const g = t.gene_symbol || t.ensembl_id; return [g, direct[g] > 0 ? fmtN(direct[g]) : "none", String(shared[g] ? shared[g].size : 0)]; }))}</figure>`;
}
async function viewMechanism(arg) {
  if (!rankingCache || rankingCache.__error) rankingCache = await api("/api/ranking");
  const rows = arr((rankingCache || {}).rows).slice().sort((a, b) => (b.molecular ?? -1) - (a.molecular ?? -1));
  const pick = arg && rows.some(r => r.compound === arg) ? arg : (rows.find(r => r.compound === "Donepezil") || rows[0] || {}).compound;
  if (!pick) return errBox("no ranking available");
  const d = await api("/api/compound?name=" + encodeURIComponent(pick)); if (d.__error) return errBox(d.__error);
  const M = (d.dimensions || {}).molecular || {}, E = M.evidence_chain || {}, R = M.record || {}, st = ((d.completeness || {}).domains || {}).molecular || {};
  const chain = arr(E.mechanistic_chain);
  const steps = {drug_to_target: "drug → target", gene_to_disease: "target gene → PD", pathway_to_disease: "target → shared pathway → PD"};
  const html = `<section class="panel"><h2>Molecular &amp; mechanism explorer</h2>
    <p class="small">How each candidate's known drug targets connect to Parkinson's disease: directly (target–disease association) or indirectly (pathways shared with Parkinson's genes). This measures mechanistic plausibility, not whether the drug works.</p>
    ${provBox(`Molecular Plausibility agent (10b) · <code>${esc(E.source || M.source)}</code>`)}
    <label for="mechpick" class="small muted">Candidate (sorted by mechanism rank)</label>
    <select id="mechpick">${rows.map(r => `<option value="${esc(r.compound)}"${r.compound === pick ? " selected" : ""}>${esc(r.compound)} — ${typeof r.molecular === "number" ? r.molecular.toFixed(2) : "n/a"}${String(r.dimensions_missing).includes("molecular") ? " (not measured)" : ""}</option>`).join("")}</select>
    <div>${stateBadge(st.state, st.detail)} <span class="small">${linkify(st.detail || "")}</span></div>
    ${R.chembl_id ? `<div class="small">ChEMBL: ${extLink("chembl", R.chembl_id)} · score ${fmt(R.molecular_plausibility_score)} (direct target–PD ${fmt(R.direct_component)}, pathway ${fmt(R.pathway_component)}) · data-availability confidence ${fmt(R.confidence)} (how complete the target data are; not a probability of efficacy).</div>` : ""}
    ${E.explanation ? `<p class="small"><strong>${esc(E.explanation)}</strong></p>` : ""}
    <p class="small"><a href="${esc(drugHref(pick))}">Open the ${esc(pick)} candidate page</a></p>
    ${E.targets || E.status ? chartChain(pick, E) : ""}</section>
    ${E.targets ? `<section class="panel"><h2>Targets</h2>${arr(E.targets).length ? `<div class="tablewrap"><table><thead><tr><th scope="col">gene</th><th scope="col">Ensembl</th><th scope="col">action</th><th scope="col">mechanism</th></tr></thead><tbody>${E.targets.map(t => `<tr><td>${esc(t.gene_symbol)}</td><td>${extLink("ensembl", t.ensembl_id)}</td><td>${esc(t.action_type)}</td><td class="small">${esc(t.mechanism_of_action)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">ChEMBL lists no mechanism-of-action target: molecular evidence is absent at source, not negative.</div>'}</section>
    <section class="panel"><h2>Evidence chain (${esc(E.n_mechanistic_steps)} steps${E.n_mechanistic_steps > chain.length ? `, first ${chain.length} shown` : ""})</h2>
      ${chain.length ? `<div class="tablewrap"><table><thead><tr><th scope="col">step</th><th scope="col">from</th><th scope="col">via</th><th scope="col">to</th><th scope="col">relation</th><th scope="col">tier</th><th scope="col">strength</th><th scope="col">source</th></tr></thead><tbody>
      ${chain.map(c => `<tr><td class="small">${esc(steps[c.step] || c.step)}</td><td>${esc(c.from)}<div class="small">${/^ENSG/.test(c.from_id || "") ? extLink("ensembl", c.from_id) : /^CHEMBL/.test(c.from_id || "") ? extLink("chembl", c.from_id) : ""}</div></td>
        <td class="small">${c.via ? esc(c.via) + "<br>" + extLink("reactome", c.via_id) : ""}</td><td>${esc(c.to)}<div class="small">${/^ENSG/.test(c.to_id || "") ? extLink("ensembl", c.to_id) : esc(c.to_id || "")}</div></td>
        <td class="small">${esc(c.relation)}${c.detail ? `<div class="muted">${esc(c.detail)}</div>` : ""}</td><td>${esc(c.tier)}</td><td>${fmt(c.strength)}</td><td class="small">${esc(c.source)}</td></tr>`).join("")}</tbody></table></div>` : '<div class="empty">No chain steps recorded.</div>'}</section>
    <section class="panel"><h2>Target → Parkinson's association</h2>
      <div class="small muted">Only association data types that cannot encode the evaluation outcome are used; clinical and literature association scores are excluded to avoid leakage and shown for transparency.</div>
      ${table(arr(E.disease_links).map(x => ({gene: x.gene_symbol, score_used: x.score_allowed_datatypes, datatypes_used: x.datatype_scores_used, excluded_for_leakage: x.datatype_scores_excluded_for_leakage})))}</section>
    <section class="panel"><h2>Pathways (${esc(E.n_pathways)})</h2>${table(arr(E.pathways).slice().sort((a, b) => (b.in_disease_module === true) - (a.in_disease_module === true)).map(p => ({pathway: p.pathway_name, id: p.pathway_id, gene: p.gene_symbol, top_level: p.top_level_term, shares_PD_gene: p.in_disease_module, tier: p.tier})))}
      <details><summary>Limitations recorded by the agent</summary><ul class="small">${arr(E.limitations).map(l => `<li>${esc(l)}</li>`).join("")}</ul></details></section>`
    : `<section class="panel"><div class="empty">${esc(E.status || M.status || "No molecular evidence record for this compound.")}</div></section>`}`;
  const after = () => { const s = document.getElementById("mechpick"); if (s) s.addEventListener("change", () => { location.hash = "mechanism/" + encodeURIComponent(s.value); }); };
  return {html, after};
}

async function viewConflicts(arg) {
  const cf = await api("/api/conflicts"); if (cf.__error || cf.status) return errBox(cf.__error || cf.status);
  const recs = arr(cf.records), K = cf.status_counts || {};
  const pick = arg && recs.some(r => r.compound === arg) ? arg : null;
  const shown = pick ? recs.filter(r => r.compound === pick) : recs;
  return `<section class="panel"><h2>Conflicting evidence</h2>
    <p class="small">Directional claims about the same drug (curated publication findings, FDA labels, Open Targets) are compared and each disagreement is classified: different populations, doses or endpoints; a difference in statistical significance only; a real contradiction; or tension between evidence types (for example mechanism versus safety). Disagreements are never averaged into the score.</p>
    ${provBox(`Conflict &amp; Context agent (10d) · <code>${esc(cf.source)}</code> · ${esc(cf.agent_version)} · ${esc(cf.integration)}`)}
    <div>${Object.entries(K).filter(([, n]) => n).map(([k, n]) => `<span class="chip">${badge(k)} ${esc(n)}</span>`).join("")}</div>
    <div class="small muted">"Insufficient evidence" (${esc(K.INSUFFICIENT || 0)} candidates) means fewer than two directional sources, which is not the same as agreement. Those candidates are not listed below.</div>
    <nav class="flow" aria-label="Candidates with assessed conflicts"><a class="chip" href="#conflicts"${pick ? "" : ' aria-current="page"'}>all ${esc(recs.length)}</a>${recs.map(r => `<a class="chip" href="#conflicts/${esc(encodeURIComponent(r.compound))}"${r.compound === pick ? ' aria-current="page"' : ""}>${esc(r.compound)}</a>`).join("")}</nav></section>
    ${shown.map(r => `<h3 class="cmp-h"><a href="${esc(drugHref(r.compound))}">${esc(r.compound)}</a>${r.in_evaluable_pool ? "" : ' <span class="small muted">(not in the evaluable pool)</span>'}</h3>${conflictPanel({source: cf.source, ...r})}`).join("") || '<div class="empty">No assessed records.</div>'}`;
}

async function viewReview() {
  const R = await api("/api/review"); if (R.__error || R.status) return errBox(R.__error || R.status);
  const rows = arr(R.rows), open = rows.filter(r => String(r.status).startsWith("UNRESOLVED"));
  const card = r => `<tr><td>${esc(r.priority)}</td><td>${badge(r.flag)}<div class="small muted">${esc(String(r.all_flags || "").replace(/\b[A-Z][A-Z_]{2,}\b/g, m => human(m)))}</div></td>
    <td>${extLink("nct", r.nct_id)}<div class="small">${esc(r.brief_title)}</div></td>
    <td><a href="${esc(drugHref(r.compound))}">${esc(r.compound)}</a></td>
    <td class="small">${esc(codeText(r.intervention_text))}<div class="muted">${esc(codeText(r.arm_types))}</div></td>
    <td class="small">automatic: ${esc(codeText(r.current_role_automated) || "—")}<br>from trial arms: ${esc(codeText(r.structural_reading) || "—")}<br>human decision: ${esc(codeText(r.current_role_adjudicated) || "none yet")}</td>
    <td class="small">${esc(codeText(r.reason_for_flag))}<div class="muted">${esc(codeText(r.evidence_needed))}</div></td>
    <td>${badge(String(r.status).startsWith("UNRESOLVED") ? "UNRESOLVED" : "ADJUDICATED")}</td></tr>`;
  const tbl = list => `<div class="tablewrap"><table><thead><tr><th scope="col">priority</th><th scope="col">flag</th><th scope="col">trial</th><th scope="col">compound</th><th scope="col">interventions · arms</th><th scope="col">readings of the drug's role</th><th scope="col">why it needs review · evidence needed</th><th scope="col">status</th></tr></thead><tbody>${list.map(card).join("")}</tbody></table></div>`;
  const html = `<section class="panel"><h2>Trial-role review queue</h2>
    <p class="small">Each row is a trial linked to a candidate drug where the drug's role in the trial (tested drug, co-administered, background medication) could not be settled automatically. Each needs a decision by a person; this application shows the evidence but never decides, and recording a decision happens outside the application.</p>
    <details class="small"><summary>Review policy</summary>${esc(R.policy)}</details>
    <div><span class="chip">${badge("UNRESOLVED")} ${esc(R.n_unresolved)}</span> <span class="chip">${badge("ADJUDICATED")} ${esc(R.n_adjudicated)}</span> <span class="small muted">of ${esc(R.n_links)} flagged links</span></div>
    ${chartBars(Object.entries(R.by_flag || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => ({label: human(k), value: n, text: String(n), note: k})), {title: "Why links were flagged (a link can have several reasons)", left: 200, xLabel: "links", noTable: false})}
    <details class="small"><summary>Technical details</summary>Decisions file <code>${esc(R.decision_file)}</code> · source <code>${esc(R.source)}</code> · ${esc(R.modified || "")}</details></section>
    <section class="panel"><h2>Awaiting human review (${esc(open.length)})</h2>
      <div class="filters"><label class="small">Search <input id="rq" type="search" placeholder="compound, trial ID or text"></label>
        <label class="small">Reason <select id="rflag"><option value="">any</option>${Object.keys(R.by_flag || {}).map(k => `<option value="${esc(k)}">${esc(human(k))}</option>`).join("")}</select></label>
        <span id="rcount" class="small muted" aria-live="polite"></span></div>
      <div id="rbody">${open.length ? tbl(open) : '<div class="empty">No link is waiting for review.</div>'}</div></section>
    <details class="panel"><summary>Already adjudicated by a human (${esc(rows.length - open.length)}), kept as recorded</summary>${tbl(rows.filter(r => !open.includes(r)))}</details>`;
  const after = () => {
    const q = document.getElementById("rq"), f = document.getElementById("rflag"); if (!q || !f) return;
    const render = () => {
      const t = q.value.trim().toLowerCase();
      const hits = open.filter(r => (!f.value || String(r.all_flags || r.flag).includes(f.value))
        && (!t || [r.compound, r.nct_id, r.brief_title, r.intervention_text, r.reason_for_flag].some(v => String(v || "").toLowerCase().includes(t))));
      document.getElementById("rcount").textContent = `${hits.length} of ${open.length} shown`;
      document.getElementById("rbody").innerHTML = hits.length ? tbl(hits) : '<div class="empty">No waiting link matches. Clear the search or choose another reason.</div>';
    };
    q.addEventListener("input", render); f.addEventListener("change", render); render();
  };
  return {html, after};
}

const MAX_COMPARE = 4;
async function viewCompare(arg) {
  if (!rankingCache || rankingCache.__error) rankingCache = await api("/api/ranking");
  const all = arr((rankingCache || {}).rows).map(r => r.compound);
  let names = String(arg || "").split(",").map(s => s.trim()).filter(n => all.includes(n));
  names = [...new Set(names)].slice(0, MAX_COMPARE);
  if (!names.length) names = all.slice(0, 2);
  const ds = await Promise.all(names.map(n => api("/api/compound?name=" + encodeURIComponent(n))));
  const r3 = x => typeof x === "number" ? x.toFixed(3) : "—";
  const row = (label, f) => `<tr><th scope="row">${esc(label)}</th>${ds.map(d => `<td>${d.__error ? '<span class="bad">error</span>' : f(d)}</td>`).join("")}</tr>`;
  const dim = k => d => { const s = ((d.completeness || {}).domains || {})[k] || {}, v = ((d.dimensions || {})[k] || {}).in_vps || {};
    return `${bar(v["r_" + k], k)} ${fmt(v["r_" + k])}<div>${stateBadge(s.state, s.detail)}</div>`; };
  const html = `<section class="panel"><h2>Compare candidates</h2>
    <p class="small">Up to ${MAX_COMPARE} candidates side by side, from the saved results. Ranks are percentiles within the 90 evaluated drugs; each value says whether it was measured, measured as zero, or is missing.</p>
    ${vpsProvenance()}
    <div class="filters"><label class="small">Add <select id="cmpadd"><option value="">choose a candidate…</option>${all.filter(n => !names.includes(n)).map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("")}</select></label>
      ${names.map(n => `<span class="chip">${esc(n)} <button type="button" class="x" data-rm="${esc(n)}" aria-label="Remove ${esc(n)}">×</button></span>`).join("")}</div></section>
    <section class="panel"><h2>Score components</h2>${chartDims(names.map(n => arr(rankingCache.rows).find(r => r.compound === n)).filter(Boolean), {title: "Dimension ranks of the compared candidates"})}
      <div class="small muted">Grouped bars are used instead of a radar chart so that missing dimensions and equal scales stay readable.</div></section>
    <section class="panel"><div class="tablewrap cmp"><table><thead><tr><th scope="col"></th>${ds.map((d, i) => `<th scope="col"><a href="${esc(drugHref(names[i]))}">${esc(names[i])}</a></th>`).join("")}</tr></thead><tbody>
      ${row("rank (5-dimension score)", d => { const f = ((d.pool || {}).fused_scores || {}).VPS_equal_5d || {}; return `${fmt(f.rank)} / ${fmt(f.of)} · VPS ${r3(f.score)}`; })}
      ${row("outcome", d => (d.pool || {}).label === 1 ? "entered Parkinson's trials after 2020" : "no Parkinson's trial after 2020 found")}
      ${row("clinical maturity", dim("clinical"))}${row("literature independence", dim("literature"))}${row("safety", dim("safety"))}
      ${row("mechanism (molecular)", dim("molecular"))}${row("network proximity", dim("proximity"))}
      ${row("pre-cutoff trials", d => { const t = arr(((d.dimensions || {}).clinical || {}).precutoff_trials_feature?.trials); return `${t.length} · max phase rank ${fmt((((d.dimensions || {}).clinical || {}).in_vps || {}).max_phase_rank)}`; })}
      ${row("safety concerns", d => arr((d.summary || {}).safety_concerns).map(c => `<div class="small">${linkify(c.text)}</div>`).join("") || '<span class="small muted">none listed</span>')}
      ${row("supporting / null-opposing claims", d => `${arr((d.summary || {}).supporting).length} / ${arr((d.summary || {}).null_or_opposing).length}`)}
      ${row("top targets", d => arr((((d.dimensions || {}).molecular || {}).evidence_chain || {}).targets).slice(0, 4).map(t => esc(t.gene_symbol)).join(", ") || '<span class="muted small">none recorded</span>')}
      ${row("conflicting evidence", d => badge((d.conflict_context || {}).status || "—"))}
      ${row("replication of findings", d => arr((d.reproducibility || {}).findings).map(f => `<div class="small">${esc(f.finding.split(":")[1])}: ${badge(f.status)}</div>`).join("") || '<span class="muted small">not assessed</span>')}
      ${row("evidence gaps", d => `${arr((d.completeness || {}).gaps).length}<div class="small muted">${arr((d.completeness || {}).gaps).slice(0, 3).map(g => esc(g.domain.replace(/_/g, " "))).join(", ")}</div>`)}
    </tbody></table></div></section>`;
  const after = () => {
    const s = document.getElementById("cmpadd");
    if (s) s.addEventListener("change", () => { if (s.value) location.hash = "compare/" + [...names, s.value].slice(-MAX_COMPARE).map(encodeURIComponent).join(","); });
    document.querySelectorAll("button[data-rm]").forEach(b => b.addEventListener("click", () => {
      location.hash = "compare/" + names.filter(n => n !== b.dataset.rm).map(encodeURIComponent).join(","); }));
  };
  return {html, after};
}

// Dependency-aware freshness from the run tracker (an upstream STALE stage makes the agent STALE even when its
// own output and input hashes are unchanged).
function trackedCell(a) {
  const t = arr(a.tracked_runs);
  if (!t.length) return '<span class="muted">no tracked stage</span>';
  return `${badge(a.tracked_status || "UNKNOWN")}${t.map(x => `<div><code>${esc(x.stage)}</code> ${esc(x.status)}${x.last_success_utc ? ` · ${esc(x.last_success_utc)}` : ""}${x.duration_s != null ? ` · ${esc(dur(x.duration_s))}` : ""}${x.status === "RUNNING" && x.elapsed_s != null ? ` · running ${esc(dur(x.elapsed_s))}` : ""}${arr(x.reasons).length ? `<div class="warn">${x.reasons.map(esc).join("; ")}</div>` : ""}</div>`).join("")}`;
}

function runCell(r) {
  r = r || {};
  if (!r.run_status && !r.generated_utc) return '<span class="muted">no run record</span>';
  const diags = arr(r.outputs).flatMap(o => arr(o.diagnostics));
  return `${r.run_status ? badge(r.run_status) : '<span class="muted">no envelope</span>'}<div class="muted">${esc(r.generated_utc || "")}</div>
    ${arr(r.stale_inputs).length ? `<div class="bad">inputs changed: ${r.stale_inputs.slice(0, 3).map(esc).join(", ")}</div>` : ""}
    ${diags.length ? `<details><summary>${diags.length} diagnostic(s)</summary><ul>${diags.map(d => `<li>${esc(d.level)} ${esc(d.code)}: ${esc(d.message)}</li>`).join("")}</ul></details>` : ""}`;
}

async function viewTechnical() {
  const [g, RM] = await Promise.all([api("/api/agents"), api("/api/runmeta")]);
  return `<section class="panel"><h2>Advanced diagnostics</h2>
    <p class="small">For checking how results were produced: stage identifiers, file paths, fingerprints, logs, connectors and project documents. Nothing on these pages runs a stage, a test or a network request.</p>
    <ul><li><a href="#pipeline">Stages, files and fingerprints</a> — what each stage reads and writes, run records, log tails.</li>
      <li><a href="#agents">Agents, connectors and data sources</a> — agent inventory, external endpoints, credential names (never values), output schemas.</li>
      <li><a href="#cases">Case studies and project documents</a> — verification ledger and the canonical decision, issue and change logs.</li></ul>
    ${RM.status ? `<div class="small warn">Test history: ${esc(RM.status)}.</div>` : `<div class="small">Last recorded test run: ${esc(RM.total)} tests, ${esc(RM.failures)} failures, ${esc(RM.errors)} errors, ${esc(RM.skipped)} skipped · finished ${esc(RM.finished_utc)} · git ${esc(RM.git_head || "")}</div>`}</section>
    ${g.__error ? errBox(g.__error) : `<section class="panel"><h2>Agent status</h2><div class="tablewrap"><table><thead><tr><th scope="col">id</th><th scope="col">agent</th><th scope="col">implementation status</th><th scope="col">tracked freshness</th><th scope="col">last run</th></tr></thead><tbody>
      ${arr(g.agents).map(a => `<tr><td class="nowrap"><a href="#agent/${esc(a.id)}">${esc(a.id)}</a></td><td>${esc(a.name)}</td><td>${badge(a.status)}</td><td class="small">${trackedCell(a)}</td><td class="small">${runCell(a.run)}</td></tr>`).join("")}</tbody></table></div><div class="small muted">${esc(g.note)}</div></section>`}`;
}

function vpsProvenance() {
  const v = (lastStatus || {}).vps;
  if (!v) return '<div class="small muted">Result-set status unavailable.</div>';
  const sc = v.scoring || {}, pend = arr((lastStatus || {}).pending_candidates), on = runDate(v.displayed_run_id);
  const fresh = {SUCCESS: "", ADOPTED: "", STALE: '<span class="warn"> Inputs have changed since this result was produced.</span>', FAILED: '<span class="bad"> The latest recomputation failed; this is the retained earlier result.</span>',
    RUNNING: '<span class="warn"> A recomputation is running; the retained result is shown until it is verified.</span>'}[v.status];
  return `<div class="small">Scores are from the approved result set${on ? ` recorded ${esc(on)}` : ""}; an independent recomputation ${v.validation_ok === true ? '<span class="ok">matched</span>' : v.validation_ok === false ? '<span class="bad">did not match</span>' : "was not recorded"}.${fresh ?? ` <span class="warn">${esc(human(v.status))}.</span>`}${pend.length ? " An unapproved alternative result set exists and is not shown." : ""}</div>
    <details class="prov"><summary>Source and provenance</summary><code>data/vps_scores_v2.csv</code> · run <code>${esc(v.displayed_run_id || "none")}</code> · ${esc(human(v.status))} (<code>${esc(v.status)}</code>) · ${esc(sc.model || "")}${sc.rank_convention ? " · rank convention " + esc(sc.rank_convention) : ""}${pend.map(c => ` · pending result set <code>${esc(c.name)}</code> (${c.independently_verified ? "independently verified" : "verification failed or incomplete"}; not approved)`).join("")}</details>`;
}

const dur = s => s == null ? "" : s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
function logLink(r) {
  return r && r.log ? ` · <details class="logtail" data-run="${esc(r.run_id)}"><summary>log</summary><div class="small muted"><code>${esc(r.log)}</code></div><pre class="small">loading…</pre></details>` : "";
}
// Log tails are fetched only when a reader opens one (never by the poll).
document.addEventListener("toggle", async e => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("logtail") || !d.open) return;
  const pre = d.querySelector("pre");
  const r = await api("/api/log?run_id=" + encodeURIComponent(d.dataset.run));
  pre.textContent = r.__error || r.error ? `log unavailable: ${r.__error || r.error}` : (r.tail || "(empty log)") + (r.bytes > 65536 ? `\n… last ${r.tail_lines} lines of ${r.bytes} bytes` : "");
}, true);

function runTable(st) {
  if (!st || st.__error) return errBox((st || {}).__error || "status unavailable");
  return `<section class="panel"><h2>Tracked runs and freshness</h2>
    <p class="small muted">From <code>data/run_manifest.json</code> (written only by <code>scripts/run_stage.py</code>). Freshness compares content fingerprints of each stage's inputs and outputs with those recorded at its last success, and propagates along dependencies — a timestamp alone never counts as fresh. ADOPTED = outputs that existed before tracking began (fingerprinted, not re-run).</p>
    <div class="small">Run a stage from the repository root: <code>${esc(st.commands.run_stage)}</code> · status: <code>${esc(st.commands.status)}</code>. Live monitoring: this page polls the local run manifest and artefact fingerprints every few seconds and re-renders when they change. It never fetches external evidence or starts a stage.</div>
    <div class="tablewrap"><table><thead><tr><th scope="col">stage</th><th scope="col">status</th><th scope="col">last success</th><th scope="col">latest attempt</th><th scope="col">upstream</th><th scope="col">why</th></tr></thead><tbody>
    ${arr(st.stages).map(x => `<tr><td><strong>${esc(x.id)}</strong> <span class="small muted">${esc(x.name)}</span></td><td>${badge(x.status)}${x.status === "RUNNING" && x.elapsed_s != null ? `<div class="small">running for ${esc(dur(x.elapsed_s))} (no progress measure)</div>` : ""}</td>
      <td class="small">${x.last_success ? `<code>${esc(x.last_success.run_id)}</code><div class="muted">${esc(x.last_success.finished_utc || "")}${x.last_success.duration_s != null ? " · took " + esc(dur(x.last_success.duration_s)) : ""}</div>${x.code_fingerprint_recorded === false ? '<div class="muted">no code fingerprint recorded: later code changes are not detected for this result</div>' : ""}` : '<span class="muted">none</span>'}</td>
      <td class="small">${x.last_attempt ? `${badge(x.last_attempt.status)} <code>${esc(x.last_attempt.run_id)}</code>${x.last_attempt.started_utc ? " · started " + esc(x.last_attempt.started_utc) : ""}${x.last_attempt.duration_s != null ? " · " + esc(dur(x.last_attempt.duration_s)) : ""}${x.last_attempt.exit_code != null ? " · exit " + esc(x.last_attempt.exit_code) : ""}${logLink(x.last_attempt)}` : '<span class="muted">none</span>'}
        ${arr((x.last_attempt || {}).diagnostics).filter(d => d.level !== "info").map(d => `<div class="${d.level === "error" ? "bad" : "warn"}">${esc(d.code)}: ${esc(d.message)}</div>`).join("")}</td>
      <td class="small">${arr(x.upstream).map(u => `${esc(u.id)} ${badge(u.status || "?")}`).join(" ") || '<span class="muted">—</span>'}</td>
      <td class="small">${arr(x.reasons).concat(arr(x.warnings)).map(esc).join("<br>") || '<span class="muted">—</span>'}</td></tr>`).join("")}</tbody></table></div>
    ${arr(st.history).length ? `<details><summary>Recent runs (${st.history.length})</summary>${table(st.history.slice().reverse())}</details>` : ""}</section>`;
}

async function viewPipeline() {
  const [p, RM, ST] = await Promise.all([api("/api/pipeline"), api("/api/runmeta"), api("/api/status")]); if (p.__error) return errBox(p.__error);
  const stages = arr(p.stages);
  const RS = Object.fromEntries(arr((ST || {}).stages).map(x => [x.id, x.status]));   // content/dependency-based
  const sb = s => RS[s.id] ? `${badge(RS[s.id])} <span class="small muted">files: ${esc(s.status)}</span>` : `<span class="small muted">files: ${esc(s.status)}</span>`;
  const runs = `<section class="panel"><h2>Run &amp; audit status</h2>
    <p class="small muted">Artefact presence is not proof that a stage ran successfully. The dashboard never runs a stage or a test; it shows what is on disk.</p>
    ${RM.status ? `<div class="warn small">Test run metadata ${esc(RM.status)} (<code>${esc(RM.source)}</code>).</div>`
      : `<div class="small">Last recorded test run (<code>${esc(RM.source)}</code>): ${RM.ok ? '<span class="ok">all passed</span>' : '<span class="bad">failures recorded</span>'} · ${esc(RM.total)} tests · ${esc(RM.failures)} failures · ${esc(RM.errors)} errors · ${esc(RM.skipped)} skipped · ${esc(RM.started_utc)} → ${esc(RM.finished_utc)} · Python ${esc(RM.python)} · git ${esc(RM.git_head)}</div>
        <details><summary>Per test module</summary>${table(Object.entries(RM.modules || {}).map(([m, c]) => ({module: m, ...c})))}</details>
        ${arr(RM.failed_tests).length ? `<div class="bad small">Failed: ${RM.failed_tests.map(esc).join(", ")}</div>` : ""}`}</section>`;
  const order = stages.map(s => `<span class="node">${esc(s.id)} ${esc(String(s.name).split(" (")[0])} ${sb(s)}</span>`).join('<span class="muted" aria-hidden="true">→</span>');
  return runTable(ST) + runs + `<div class="panel"><h2>Pipeline stages and artefacts</h2>
    <p class="small muted">${esc(p.note)} Temporal cutoff: <code>${esc(p.cutoff_date)}</code>.</p>
    <div class="flow">${order}</div>
    <details class="small"><summary>Status legend</summary><ul>${Object.entries(p.status_legend || {}).map(([k,v]) => `<li>${badge(k)} ${esc(v)}</li>`).join("")}</ul></details></div>
  ${stages.map(s => `<section class="panel" aria-labelledby="st-${esc(s.id)}"><h2 id="st-${esc(s.id)}">${esc(s.id)} · ${esc(s.name)} ${sb(s)}</h2>
    <div class="small"><code>${esc(s.script)}</code> ${s.script_exists ? "" : '<span class="bad">script missing</span>'}
      · depends on: ${arr(s.depends_on).length ? arr(s.depends_on).map(d => `<span class="chip">${esc(d)}</span>`).join("") : '<span class="muted">none</span>'}
      · ${esc(s.persistence)}</div>
    <p>${esc(s.purpose)}</p>
    ${arr(s.health).map(h => `<div class="small ${h.level === "warn" ? "warn" : "muted"}">${h.level === "warn" ? "Warning: " : "Note: "}${esc(h.text)}</div>`).join("")}
    <h3>Inputs</h3>${files(s.inputs)}
    <h3>Outputs</h3>${files(s.outputs)}
    ${s.checkpoint ? `<h3>Checkpoint</h3>${files([s.checkpoint])}` : ""}
    ${arr(s.issues).length ? `<h3>Linked issues (from the canonical logs)</h3><ul class="small">${arr(s.issues).map(i => `<li><strong>${esc(i.id)}</strong> ${esc(i.severity)} — ${esc(i.title)} ${i.status ? `<em>${esc(i.status)}</em>` : ""}</li>`).join("")}</ul>` : ""}
  </section>`).join("")}`;
}

async function viewAgents(arg) {
  const [p, g] = await Promise.all([api("/api/pipeline"), api("/api/agents")]);
  if (p.__error) return errBox(p.__error);
  const stages = arr(p.stages), rows = [];
  if (!compoundsCache || compoundsCache.__error) compoundsCache = await api("/api/compounds");
  const pool = arr((compoundsCache || {}).compounds).filter(x => x.in_pool).map(x => x.name);
  const pick = arg && pool.includes(arg) ? arg : (pool.includes("Melatonin") ? "Melatonin" : pool[0]);
  const inv = g.__error ? errBox(g.__error) : `<section class="panel"><h2>Specialised evidence agents (architecture 10a–10h)</h2>
    <div class="small muted">${esc(g.note)}</div>
    <div class="tablewrap"><table><thead><tr><th scope="col">id</th><th scope="col">agent</th><th scope="col">status</th><th scope="col">tracked freshness</th><th scope="col">last run</th><th scope="col">module</th><th scope="col">tests</th><th scope="col">scope / source coverage</th><th scope="col">outputs &amp; schema</th></tr></thead><tbody>
    ${arr(g.agents).map(a => `<tr><td class="nowrap"><strong>${esc(a.id)}</strong></td><td>${esc(a.name)}${a.vps_role ? `<div class="small muted">${esc(a.vps_role)}</div>` : ""}</td><td>${badge(a.status)}</td>
      <td class="small">${trackedCell(a)}</td>
      <td class="small">${runCell(a.run)}</td>
      <td>${a.module ? `<code>${esc(a.module)}</code>${a.module_exists ? "" : ' <span class="bad">missing</span>'}` : '<span class="muted">—</span>'}</td>
      <td>${a.n_test_functions != null ? esc(a.n_test_functions) + " test functions" : '<span class="muted">none</span>'}${a.latest_test_run ? `<div class="small ${a.latest_test_run.failures || a.latest_test_run.errors ? "bad" : "ok"}">last run: ${esc(a.latest_test_run.tests)} run, ${esc(a.latest_test_run.failures + a.latest_test_run.errors)} failed</div>` : (a.tests ? '<div class="small muted">no recorded run</div>' : "")}</td>
      <td class="small">${esc(a.scope)}<div class="muted">Sources: ${esc(a.sources)}</div></td>
      <td class="small">${arr(a.outputs).map(o => `<div><code>${esc(o.path)}</code> ${o.exists ? `<span class="muted">${esc(o.modified)}</span>` : '<span class="bad">missing</span>'}</div>`).join("") || '<span class="muted">—</span>'}
        ${arr(a.output_schema).length ? `<details><summary>schema</summary>${a.output_schema.map(k => `<span class="chip">${esc(k)}</span>`).join("")}</details>` : ""}</td></tr>`).join("")}
    </tbody></table></div></section>`;
  const inspector = `<section class="panel"><h2>Inspect agent outputs for one candidate</h2>
    <label for="agentpick" class="small muted">Compound (evaluable pool)</label>
    <select id="agentpick">${pool.map(n => `<option value="${esc(n)}"${n === pick ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>
    <div id="agentout">${pick ? await agentOutputs(pick) : '<div class="empty">No compounds.</div>'}</div></section>`;
  stages.forEach(s => (arr(s.apis).length ? s.apis : [null]).forEach(a => rows.push({s, a})));
  const html = inv + inspector + `<div class="panel"><h2>Connectors &amp; data sources</h2>
    <p class="small muted">Endpoints and queries are copied from the scripts (a test asserts each endpoint string appears in its script).
    Environment variables are listed by <strong>name only</strong>; this UI never reads <code>.env</code> or any credential value.
    Nothing on this page calls these endpoints.</p>
    <div class="tablewrap"><table><thead><tr><th scope="col">stage</th><th scope="col">agent / step</th><th scope="col">external source</th><th scope="col">endpoint</th><th scope="col">query</th><th scope="col">auth</th><th scope="col">env vars (names)</th><th scope="col">cache / checkpoint</th><th scope="col">status</th></tr></thead><tbody>
    ${rows.map(({s, a}) => `<tr><td>${esc(s.id)}</td><td>${esc(s.name)}</td>
      <td>${a ? esc(a.name) : '<span class="muted">local only</span>'}</td>
      <td>${a ? `<code>${esc(a.endpoint)}</code>` : ""}</td><td class="small">${a ? esc(a.query) : ""}</td>
      <td>${a ? esc(a.auth) : ""}</td><td>${arr(s.env).map(e => `<code>${esc(e)}</code>`).join(" ") || '<span class="muted">—</span>'}</td>
      <td class="small">${s.checkpoint ? (s.checkpoint.exists ? `<code>${esc(s.checkpoint.path)}</code> (${esc(s.checkpoint.records)} lines)` : `<span class="bad">${esc(s.checkpoint.path)} missing</span>`) : esc(s.persistence)}${s.id === "08" || s.id === "03" ? '<br><code>data/cache/molecular/</code> (Open Targets response cache)' : ""}</td>
      <td>${badge(s.status)}</td></tr>`).join("")}
    </tbody></table></div></div>
    ${stages.map(s => `<section class="panel"><h2>${esc(s.id)} · ${esc(s.name)}</h2>
      <p>${esc(s.purpose)}</p><div class="small">Cost: ${esc(s.cost)}</div>
      ${arr(s.limitations).length ? `<h3>Limitations / temporal concerns</h3><ul class="small">${s.limitations.map(l => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
      <h3>Output schemas</h3>${arr(s.outputs).map(o => `<div class="small"><code>${esc(o.path)}</code>: ${o.exists ? (o.columns ? o.columns.map(c => `<span class="chip">${esc(c)}</span>`).join("") : '<span class="muted">non-tabular</span>') : '<span class="bad">missing</span>'}</div>`).join("")}
    </section>`).join("")}`;
  const after = () => {
    const sel = document.getElementById("agentpick");
    if (sel) sel.addEventListener("change", () => { location.hash = "agents/" + encodeURIComponent(sel.value); });
  };
  return {html, after};
}

async function agentOutputs(name) {
  const d = await api("/api/compound?name=" + encodeURIComponent(name)); if (d.__error) return errBox(d.__error);
  const M = (d.dimensions || {}).molecular || {}, E = M.evidence_chain || {}, LC = d.literature_credibility;
  return `<h3>10b Molecular plausibility <span class="prov">(<code>${esc(E.source || M.source)}</code>)</span></h3>
    ${E.targets ? `<div class="small"><strong>${esc(E.explanation)}</strong></div>${table(E.targets, ["gene_symbol", "action_type", "mechanism_of_action"])}` : `<div class="empty">${esc(E.status || M.status || "no molecular record")}</div>`}
    <h3>10a Literature credibility</h3>${LC ? `<div class="prov"><code>${esc(LC.source)}</code> · efficacy: ${esc(LC.efficacy)}</div>${kv(LC.summary_pre_cutoff)}` : '<div class="empty">No 10a output for this compound (run stages 04p and 10a-all).</div>'}
    ${conflictPanel(d.conflict_context)}${reproPanel(d.reproducibility)}`;
}

let compoundsCache = null;
const drugHref = n => "#drugs/" + encodeURIComponent(n);
async function viewDrugs(selected) {
  if (!compoundsCache || compoundsCache.__error) compoundsCache = await api("/api/compounds");
  const c = compoundsCache; if (c.__error) return errBox(c.__error);
  if (!rankingCache || rankingCache.__error) rankingCache = await api("/api/ranking");
  if (!reviewCache || reviewCache.__error) reviewCache = await api("/api/review");
  if (selected) return candidatePage(selected);
  const all = arr(c.compounds), outside = all.filter(x => !x.in_pool);
  const html = rankingCharts() + rankingPanel() + (outside.length ? `<details class="panel"><summary><strong>${esc(outside.length)} other compounds</strong> <span class="small muted">appear in some evidence file but are not in the evaluated set, so they have no score</span></summary>
      <ul class="list cols-list">${outside.map(x => `<li><a href="${esc(drugHref(x.name))}">${esc(x.name)}</a></li>`).join("")}</ul></details>` : "");
  const after = () => {
    const box = document.getElementById("q");
    if (!box) return;
    box.value = rankQuery;
    box.addEventListener("input", () => { rankQuery = box.value; renderRanking(); });
    const head = document.getElementById("rankhead");
    if (head) head.addEventListener("click", e => {
      const b = e.target.closest("button[data-sort]"); if (!b) return;
      rankSort = {key: b.dataset.sort, dir: rankSort.key === b.dataset.sort ? -rankSort.dir : (b.dataset.sort === "compound" || b.dataset.sort === "rank" ? 1 : -1)};
      renderRanking();
    });
    ["flabel", "fmiss", "fconf"].forEach(id => { const el = document.getElementById(id); if (!el) return;
      el.value = rankFilter[id] || "";
      el.addEventListener("change", () => { rankFilter[id] = el.value; renderRanking(); }); });
    document.getElementById("freset").addEventListener("click", () => { rankFilter = {}; rankQuery = ""; box.value = "";
      ["flabel", "fmiss", "fconf"].forEach(id => { document.getElementById(id).value = ""; }); renderRanking(); });
    renderRanking();
  };
  return {html, after};
}
let reviewCache = null, rankQuery = "";
const DIM_NAME = {proximity: "network proximity", clinical: "clinical maturity", literature: "literature independence", safety: "safety", molecular: "molecular plausibility"};
const DIMS = ["clinical", "literature", "safety", "molecular", "proximity"];
const missingOf = r => String(r.dimensions_missing || "").split("|").filter(Boolean);
const imputedOf = r => String(r.dimensions_imputed || "").split("|").filter(Boolean);
// Plain description of a candidate's rank profile: its strongest and weakest measured dimensions (no new score).
function profileText(r) {
  const m = DIMS.filter(d => !missingOf(r).includes(d) && typeof r[d] === "number").sort((a, b) => r[b] - r[a]);
  if (!m.length) return "no measured dimension";
  const hi = m.filter(d => r[d] >= 0.75), lo = m.filter(d => r[d] < 0.25);
  return (hi.length ? "Strong: " + hi.map(d => DIM_NAME[d]).join(", ") : "No dimension in the top quarter") + (lo.length ? ". Weak: " + lo.map(d => DIM_NAME[d]).join(", ") : "") + ".";
}
function reviewsFor(name) { return arr((reviewCache || {}).rows).filter(x => x.compound === name && String(x.status).startsWith("UNRESOLVED")).length; }
function limitationText(r) {
  const out = [];
  if (missingOf(r).includes("safety")) out.push("no US FDA label, so safety is not measured");
  if (missingOf(r).includes("molecular")) out.push("no known drug target, so mechanism is not measured");
  imputedOf(r).forEach(d => out.push(`${DIM_NAME[d] || d} value imputed (pool median)`));
  const n = reviewsFor(r.compound); if (n) out.push(`${n} trial link${n > 1 ? "s" : ""} awaiting human review`);
  if (["CROSS_DOMAIN_TENSION", "DIRECT_CONTRADICTION", "STATISTICAL_DISAGREEMENT"].includes(r.conflict_status)) out.push("sources disagree (" + human(r.conflict_status).toLowerCase() + ")");
  return out.length ? out.join("; ") : "none recorded beyond the study-wide limitations";
}

// Candidate detail: why it ranked, evidence for and against, mechanism, safety, trials, gaps and provenance.
async function candidatePage(name) {
  const R = rankingCache || {}, me = arr(R.rows).find(r => r.compound === name);
  const back = `<div class="crumbs small"><a href="#drugs">Candidates</a> › ${esc(name)}</div>`;
  if (!arr((compoundsCache || {}).compounds).some(x => x.name === name))
    return back + `<section class="panel"><h2>${esc(name)}</h2><div class="empty">No saved evidence mentions this compound, and it is not among the evaluated candidates. Check the spelling or <a href="#drugs">return to the candidate table</a>.</div></section>`;
  const why = me ? `<section class="panel"><h2>Why ${esc(name)} ranks ${esc(me.rank)} of ${esc(R.of)}</h2>
      <p>Score ${esc(fmtN(me.VPS_equal_5d))}: the mean of five percentile ranks. ${esc(profileText(me))} ${missingOf(me).length ? `Not measured (given the neutral rank 0.5): ${missingOf(me).map(d => esc(DIM_NAME[d])).join(", ")}.` : "All five dimensions are measured."}</p>
      ${chartDims([me], {title: `Evidence dimension ranks for ${name}`})}
      <div class="small">Outcome used for evaluation: <strong>${me.label === 1 ? "entered a new Parkinson's trial after 2020" : "no new Parkinson's trial after 2020 found"}</strong> — continued clinical investigation, not proof of efficacy.</div>
      <div class="small warn">Key limitations: ${esc(limitationText(me))}.</div>
      <div class="actions"><a class="btn" href="#compare/${esc(encodeURIComponent(name))}">Compare with other candidates</a><a class="btn" href="#evidence/${esc(encodeURIComponent(name))}">All evidence items for ${esc(name)}</a><a class="btn" href="#mechanism/${esc(encodeURIComponent(name))}">Mechanism details</a></div></section>`
    : `<section class="panel"><h2>${esc(name)}</h2><div class="warn">Not in the evaluated set (no Parkinson's trial before 2021 was accepted for it), so it has no score. Evidence found for it is shown below.</div></section>`;
  return back + why + await compoundDetail(name);
}

// Ranked score chart (top 25), from /api/ranking (data/vps_scores_v2.csv).
function rankingCharts() {
  const R = rankingCache || {};
  if (R.__error || R.status || !arr(R.rows).length) return "";
  const rows = arr(R.rows).filter(r => r.VPS_equal_5d != null).slice(0, 25);
  return `<section class="panel"><h2>Candidate ranking</h2>
    <p class="small">The score ranks drugs by the breadth of evidence for <strong>continued clinical investigation</strong> in Parkinson's disease (equal-weight mean of five percentile ranks, 0–1). It is not a probability that a drug is effective or safe.</p>
    ${chartBars(rows.map(r => ({label: `${r.rank}. ${r.compound}`, value: r.VPS_equal_5d, text: fmtN(r.VPS_equal_5d), key: r.compound,
        cls: r.label === 1 ? "pos" : "", mark: (r.label === 1 ? "● " : "") + (missingOf(r).length || imputedOf(r).length ? "†" : ""),
        note: [r.label === 1 ? "entered a new Parkinson's trial after 2020" : "no new Parkinson's trial after 2020 found", missingOf(r).length ? "not measured: " + missingOf(r).join(", ") : "", imputedOf(r).length ? "imputed: " + imputedOf(r).join(", ") : ""].filter(Boolean).join("; ")})),
      {title: "Top 25 candidates by score", max: 1, left: 190, xLabel: "score (0–1, higher ranks first)", caption: "● entered a new Parkinson's trial after 2020 (the evaluation outcome). † a dimension is not measured (neutral 0.5) or median-imputed. Select a bar to open the candidate."})}</section>`;
}

let rankingCache = null, rankSort = {key: "rank", dir: 1}, rankFilter = {};
const rankCell = (r, d) => missingOf(r).includes(d) ? `<span class="nm">${d === "safety" ? "no FDA label" : d === "molecular" ? "no known target" : "not measured"}</span>`
  : `${fmtN(r[d], 2)}${imputedOf(r).includes(d) ? ' <span class="small warn">imputed</span>' : ""}`;
const RANK_COLS = [
  ["rank", "Rank", r => esc(r.rank)],
  ["compound", "Compound", r => `<a href="${esc(drugHref(r.compound))}">${esc(r.compound)}</a>`],
  ["VPS_equal_5d", "Score", r => esc(fmtN(r.VPS_equal_5d))],
  ["profile", "What drives the score", r => `<span class="small">${esc(profileText(r))}</span>`, false],
  ["n_dimensions_measured", "Evidence coverage", r => `${esc(r.n_dimensions_measured != null ? Number(r.n_dimensions_measured) : "—")} of 5 measured`],
  ["clinical", "Clinical (rank)", r => rankCell(r, "clinical")],
  ["safety", "Safety (rank)", r => rankCell(r, "safety")],
  ["molecular", "Mechanism (rank)", r => rankCell(r, "molecular")],
  ["conflict_status", "Conflicting evidence", r => badge(r.conflict_status)],
  ["label", "New trial after 2020", r => r.label === 1 ? "yes" : "no"],
  ["limitation", "Key limitation", r => `<span class="small">${esc(limitationText(r))}</span>`, false]];
function rankingPanel() {
  const R = rankingCache || {};
  if (R.__error || R.status) return errBox(R.__error || R.status);
  return `<section class="panel"><h2>All candidates</h2>
    <p class="small">The ${esc(arr(R.rows).length)} drugs with a Parkinson's trial before 2021, ordered by the approved score. Ranks (0–1) are percentiles within this set: higher means more favourable evidence, not a measured effect. Select a column header to sort and a name to open the candidate.</p>
    <div class="filters">
      <label class="small">Search <input id="q" type="search" placeholder="compound name" autocomplete="off" aria-controls="rankbody"></label>
      <label class="small">New trial after 2020 <select id="flabel"><option value="">any</option><option value="1">yes</option><option value="0">no</option></select></label>
      <label class="small">Evidence coverage <select id="fmiss"><option value="">any</option><option value="complete">all 5 dimensions measured</option><option value="any">some dimension not measured</option><option value="safety">safety not measured</option><option value="molecular">mechanism not measured</option></select></label>
      <label class="small">Conflicting evidence <select id="fconf"><option value="">any</option><option value="assessed">compared (two or more directional sources)</option></select></label>
      <button type="button" class="act ghost" id="freset">Clear filters</button>
      <span id="rankcount" class="small muted" aria-live="polite"></span>
    </div>
    ${vpsProvenance()}
    <div class="tablewrap rank"><table><thead id="rankhead"><tr>${RANK_COLS.map(([k, l, , sortable]) => `<th scope="col"${sortable === false ? "" : ` aria-sort="${rankSort.key === k ? (rankSort.dir > 0 ? "ascending" : "descending") : "none"}"`}>${sortable === false ? esc(l) : `<button type="button" class="sort" data-sort="${esc(k)}">${esc(l)}</button>`}</th>`).join("")}</tr></thead>
    <tbody id="rankbody"></tbody></table></div></section>`;
}
function renderRanking() {
  const body = document.getElementById("rankbody"); if (!body) return;
  const q = String(rankQuery || "").trim().toLowerCase();
  const {key, dir} = rankSort;
  const val = id => (document.getElementById(id) || {}).value || "";
  const fl = val("flabel"), fm = val("fmiss"), fc = val("fconf");
  const rows = arr((rankingCache || {}).rows).filter(r => String(r.compound).toLowerCase().includes(q))
    .filter(r => fl === "" || String(Number(r.label)) === fl)
    .filter(r => { const m = missingOf(r);
      return fm === "" || (fm === "complete" ? !m.length : fm === "any" ? m.length > 0 : m.includes(fm)); })
    .filter(r => fc === "" || !["INSUFFICIENT", "NO_COMPARABLE_PAIR", "not assessed", "NO_EVIDENCE"].includes(r.conflict_status)).slice()
    .sort((a, b) => { const x = a[key], y = b[key]; if (x === y) return 0; if (x === null || x === undefined) return 1; if (y === null || y === undefined) return -1;
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * dir; });
  body.innerHTML = rows.map(r => `<tr>${RANK_COLS.map(([k, , f]) => `<td${k === "compound" ? ' class="nowrap"' : ""}>${f(r)}</td>`).join("")}</tr>`).join("")
    || `<tr><td colspan="${RANK_COLS.length}" class="muted">No candidate matches these filters. Use "Clear filters" to see all.</td></tr>`;
  const rc = document.getElementById("rankcount"); if (rc) rc.textContent = `${rows.length} of ${arr((rankingCache || {}).rows).length} shown`;
  document.querySelectorAll("#rankhead th").forEach((th, i) => { if (RANK_COLS[i][3] !== false) th.setAttribute("aria-sort", RANK_COLS[i][0] === key ? (dir > 0 ? "ascending" : "descending") : "none"); });
}

function dimPanel(title, d, extra) {
  d = d || {};
  return `<section class="panel"><h2>${esc(title)}</h2>
    <div class="small muted">${esc(d.definition)}</div>
    <div class="small warn">Temporal: ${esc(d.temporal)}</div>
    ${d.status === "present" ? "" : `<div class="small warn">${esc(d.status || "")}</div>`}${provBox(`<code>${esc(d.source)}</code> (stage ${esc(d.stage)})`)}
    ${d.warning ? `<div class="small bad">${esc(d.warning)}</div>` : ""}
    ${d.record ? kv(d.record) : ""}
    ${d.in_vps ? `<h3>As used in the score</h3>${kv(d.in_vps)}` : ""}
    ${d.not_measured ? `<div class="small warn">${esc(d.not_measured)}</div>` : ""}
    ${extra || ""}</section>`;
}
async function compoundDetail(name) {
  const d = await api("/api/compound?name=" + encodeURIComponent(name)); if (d.__error) return errBox(d.__error);
  if (!d.known) return `<div class="panel"><h2>${esc(name)}</h2><div class="empty">No artefact contains this compound.</div></div>`;
  const P = d.pool || {}, D = d.dimensions || {};
  const head = `<div class="panel"><h2>${P.in_evaluable_pool ? "Score variants and outcome definition" : esc(d.query)}</h2>
    ${P.in_evaluable_pool ? `<details class="small"><summary>What the outcome means</summary>${esc(P.label_meaning)}</details>
      <details><summary class="small">All score variants (grid-searched variants are in-sample)</summary>${table(Object.entries(P.fused_scores || {}).map(([k, v]) => ({variant: k, score: v.score, rank: v.rank != null ? v.rank + " / " + v.of : null})))}</details>
      ${arr(P.dimensions_missing).length ? `<div class="small warn">Not measured (neutral rank 0.5): ${P.dimensions_missing.map(esc).join(", ")} · ${fmt(P.n_dimensions_measured)}/5 dimensions measured</div>` : ""}
      <div class="small muted">${esc(P.fitted_variants_note)} Ranks are not probabilities and do not imply efficacy.</div>`
      : `<div class="warn">Not in the evaluable pool (${esc(P.reason)}).</div><div class="small muted">${esc(P.label_meaning)}</div>`}
    <details class="small"><summary>Technical details: source files</summary>${arr(d.found_in).map(f => `<code>${esc(f)}</code>`).join(" ") || "—"}</details>
    ${arr(d.missing_sources).length ? `<div class="small bad">Missing artefacts: ${d.missing_sources.map(esc).join(", ")}</div>` : ""}
    </div>`;

  const C = D.clinical || {}, A = C.match_audit || {};
  const trials = (blk, title) => { blk = blk || {}; return `<h3>${title} <span class="prov">(<code>${esc(blk.source)}</code>)</span></h3>` +
    (blk.status ? `<div class="bad small">${esc(blk.status)}</div>` : table(blk.trials, ["nct_id","phase","status","first_posted","matched_intervention","matched_alias","match_source"].concat(blk.exclusions_source ? ["excluded_from_label"] : []))); };
  const clinical = `<section class="panel"><h2>Clinical maturity &amp; ground truth</h2>
    <div class="small muted">${esc(C.definition)}</div><div class="small warn">Temporal: ${esc(C.temporal)}</div>
    ${C.in_vps ? kv(C.in_vps) : ""}
    ${trials(C.precutoff_trials_feature, "Pre-cutoff trials (FEATURE)")}
    ${trials(C.postcutoff_trials_label_only, "Post-cutoff trials (LABEL only — never a feature)")}
    <h3>Intervention-matching audit <span class="prov">(<code>${esc(A.source)}</code>)</span></h3>
    ${A.status ? `<div class="bad small">${esc(A.status)}</div>` :
      `<div class="small muted">${esc(A.policy)}</div>
       <details><summary>${arr(A.decisions).length} decisions</summary>${table(A.decisions, ["nct_id","cohort","outcome","qualifies","matched_intervention","brief_title","interventions","reason"])}</details>`}
  </section>`;

  const L = D.literature || {}, G = L.paper_graph;
  const graph = G && G.papers ? `<h3>Persisted paper graph <span class="prov">(<code>${esc(G.source)}</code>, verified against ${esc(G.verified_against)})</span></h3>
      <div class="small">counts: ${fmt(G.counts)} · component sizes: ${fmt(G.component_sizes)}</div>
      <details><summary>${arr(G.papers).length} papers, ${arr(G.edges).length} edges</summary>
      ${table(arr(G.papers).slice().sort((a, b) => (a.component ?? 0) - (b.component ?? 0)), ["component","pmid","year","title","n_authors"])}
      ${table(G.edges, ["source","target","reason"])}</details>`
    : `<div class="small muted">${esc(G ? G.status : "")}</div>`;

  const M = D.molecular || {}, E = M.evidence_chain || {};
  const chain = E.targets ? `<div class="small muted">${esc(M.confidence_note)}</div>
      <div class="prov">Evidence chain: <code>${esc(E.source)}</code></div>
      <div class="small"><strong>${esc(E.explanation)}</strong></div>
      <h3>Targets (ChEMBL via Open Targets)</h3>${table(E.targets)}
      <h3>Target → PD links</h3>${table(arr(E.disease_links).map(x => ({gene: x.gene_symbol, permitted_score: x.score_allowed_datatypes, used: x.datatype_scores_used, excluded_for_leakage: x.datatype_scores_excluded_for_leakage})))}
      <details><summary>Limitations recorded by the agent</summary><ul class="small">${arr(E.limitations).map(l => `<li>${esc(l)}</li>`).join("")}</ul></details>`
    : `<div class="small muted">${esc(E.status || "")}</div>`;

  const LC = d.literature_credibility;
  const cred = LC ? `<h3>Literature credibility (study-design quality; diagnostic, not in the score)</h3>${provBox(`Literature Credibility agent (10a) · <code>${esc(LC.source)}</code>`)}
      <div class="small muted">Study-design tiers from PubMed PublicationType; efficacy: ${esc(LC.efficacy)}.${LC.note ? " " + esc(LC.note) + "." : ""}${LC.status_10a && LC.status_10a !== "ASSESSED" ? " Status: " + esc(LC.status_10a) + "." : ""}</div>${LC.summary_pre_cutoff ? kv(LC.summary_pre_cutoff) : ""}` : "";
  const mech = `<section class="panel"><h2>Mechanism: drug → target → Parkinson's disease</h2>${E.targets || E.status ? chartChain(d.query, E) : `<div class="empty">${esc(M.status || "No molecular record for this compound.")}</div>`}
    <p class="small"><a href="#mechanism/${esc(encodeURIComponent(d.query))}">Pathways and the full evidence chain</a></p></section>`;
  return summaryPanel(d.summary, P) + mech + safetyPanel({...d.safety_evidence}) + clinicalPanel({compound: d.query, ...d.clinical_evidence}) + conflictPanel(d.conflict_context) +
    completenessPanel(d.completeness) + (P.in_evaluable_pool ? `<section class="panel">${evidenceStates(d)}</section>` : "") + independencePanel(d.evidence_independence) + head +
    `<details class="more"><summary>Detailed evidence by source (replication, the five dimensions, trials, papers)</summary>` +
    reproPanel(d.reproducibility) + dimPanel("Network proximity", D.proximity) + clinical +
    dimPanel("Literature independence", L, graph + cred) + dimPanel("Safety signal", D.safety) +
    dimPanel("Molecular / pathway plausibility", M, chain) + "</details>";
}

const CASE_KEYS = ["CASE_STUDIES", "REFERENCES", "INTERVENTION_MATCHING", "MOLECULAR_AGENT", "TECHNICAL_DEBT", "ERRORS_AND_BLOCKERS", "CHANGES", "README"];
async function viewCases(arg) {
  const key = CASE_KEYS.includes(arg) ? arg : "CASE_STUDIES";
  const d = await api("/api/doc?key=" + encodeURIComponent(key)); if (d.__error) return errBox(d.__error);
  let ledger = "";
  if (key === "CASE_STUDIES") {
    const [cf, cs] = await Promise.all([api("/api/conflicts"), api("/api/case_status")]);
    const crit = v => v === true ? '<span class="ok">✓</span>' : v === "not_applicable" ? '<span class="muted">n/a</span>' : v === false ? '<span class="bad">✗</span>' : `<span class="warn">partial</span>`;
    const CD = cs.criteria_definitions || {}, ck = Object.keys(CD);
    ledger += cs.__error || cs.status ? errBox(cs.__error || cs.status) : `<section class="panel"><h2>Case-study verification status</h2>
      <div class="small muted">Seven shortlisted candidates plus Droxidopa. <em>Documented status</em> is the verdict recorded in CASE_STUDIES.md; the criteria columns apply a fixed checklist (hover a header for its definition). A trial's existence is never evidence of benefit. <code>${esc(cs.source)}</code></div>
      <div class="tablewrap"><table><thead><tr><th scope="col">compound</th><th scope="col">rank / label</th><th scope="col">documented status</th>${ck.map(k => `<th scope="col" title="${esc(CD[k])}">${esc(k.replace(/_/g, " "))}</th>`).join("")}<th scope="col">replication (10e)</th></tr></thead><tbody>
      ${arr(cs.cases).map(c => `<tr><td><a href="${esc(drugHref(c.compound))}">${esc(c.compound)}</a><div class="small muted">${esc(c.section)}</div></td>
        <td>${c.in_pool ? `${fmt(c.rank)} / ${fmt(c.label)}` : '<span class="muted">not in pool</span>'}</td><td>${badge(c.documented_status)}</td>
        ${ck.map(k => `<td title="${esc(typeof c.criteria[k] === "string" ? c.criteria[k] : "")}">${crit(c.criteria[k])}</td>`).join("")}
        <td class="small nowrap">${arr(c.replication).map(r => `${esc(r.finding.split(":")[1])}: ${badge(r.status)}`).join("<br>") || '<span class="muted">—</span>'}</td></tr>
        <tr><td></td><td colspan="${ck.length + 3}" class="small"><strong>Verdict:</strong> ${esc(c.verdict)}
          ${arr(c.supporting).length ? `<div><span class="ok">Supporting:</span> ${c.supporting.map(esc).join("; ")}</div>` : ""}
          ${arr(c.null_or_opposing).length ? `<div><span class="warn">Null / opposing:</span> ${c.null_or_opposing.map(esc).join("; ")}</div>` : ""}
          ${arr(c.trials).length ? `<div>Trials: ${c.trials.map(t => `<code>${esc(t.id)}</code> ${esc(t.role)}`).join("; ")}</div>` : ""}
          <div class="muted">${esc(c.trial_existence_vs_benefit)}</div>
          ${arr(c.unresolved).length ? `<div class="warn">Unresolved: ${c.unresolved.map(esc).join(" ")}</div>` : ""}</td></tr>`).join("")}
      </tbody></table></div></section>`;
    const recs = arr(cf.records).filter(r => (r.coverage || {}).curated_claims > 0);
    ledger += cf.__error ? errBox(cf.__error) : `<section class="panel"><h2>Case-study evidence ledger (agent 10d)</h2>
      <div class="small muted">Claims transcribed from this document with their PMIDs; supporting vs null/opposing findings, and how 10d classifies each disagreement. <code>${esc(cf.source)}</code></div>
      ${recs.length ? recs.map(r => { const cl = arr(r.claims).filter(c => c.source_type === "curated_doc");
        const col = dirs => cl.filter(c => dirs.includes(c.direction)).map(c => `<li><strong>${esc(c.source_id)}</strong> (${esc(c.source_date || "n/a")}) ${esc(c.endpoint_measure || c.endpoint_domain)} — ${esc(c.excerpt)}</li>`).join("") || '<li class="muted">none recorded</li>';
        return `<h3><a href="${esc(drugHref(r.compound))}">${esc(r.compound)}</a> ${badge(r.status)} ${r.in_evaluable_pool ? "" : '<span class="muted small">(not in evaluable pool)</span>'}</h3>
          <div class="cols"><div><div class="small ok">Supporting</div><ul class="small">${col(["SUPPORTS"])}</ul></div>
          <div><div class="small warn">Null or opposing</div><ul class="small">${col(["NULL_RESULT", "OPPOSES"])}</ul></div></div>
          <div class="small">${arr(r.comparisons).filter(c => c.classification !== "NON_COMPARABLE").slice(0, 3).map(c => `${badge(c.classification)} ${esc(c.rationale)}`).join("<br>")}</div>`; }).join("")
        : '<div class="empty">No curated claims found.</div>'}</section>`;
  }
  return ledger + `<div class="panel"><nav class="flow" aria-label="Documents">${CASE_KEYS.map(k => `<a href="#cases/${k}" class="chip"${k === key ? ' aria-current="page"' : ""}>${esc(k)}</a>`).join("")}</nav>
    <div class="prov"><code>${esc(d.path)}</code> ${d.modified ? "· modified " + esc(d.modified) : ""} · rendered read-only; credential-like values and home-directory paths are redacted.</div></div>
    <article class="panel md">${d.status ? `<div class="empty">Document ${esc(d.status)}.</div>` : md(d.text)}</article>`;
}

// Charts built from /api/validation_charts: curves come from the approved scores and labels and are drawn only when
// their areas equal the approved report's AUROC/AUPRC; every other value is copied from the approved report.
const modelName = m => ({"equal-weight 5d (primary)": "Score, 5 dimensions (primary)", "equal-weight 4d (primary)": "Score, 4 dimensions (sensitivity)",
  "molecular only (baseline)": "Molecular dimension only (baseline)"}[m] || m);
const EVAL_TYPE = {unfitted: "Unfitted: no weights tuned on these labels", insample: "In-sample: weights tuned on these same labels (optimistic)",
  heldout: "Held-out: nested cross-validation, weights chosen on training folds only", exploratory: "Exploratory / sensitivity analysis"};
const evalTag = k => `<span class="etag et-${esc(k)}" title="${esc(EVAL_TYPE[k])}">${esc({unfitted: "Unfitted", insample: "In-sample", heldout: "Held-out", exploratory: "Exploratory"}[k])}</span>`;
// The approved result set's data contract (/api/result_set): files, run, cohort, cutoff, scoring version, fingerprints.
function resultSetPanel(RS) {
  if (!RS || RS.__error || RS.status) return errBox((RS || {}).__error || (RS || {}).status || "result-set contract unavailable");
  const C = RS.cohort || {}, E = RS.evaluation || {};
  const rows = [["Result set", `approved scores <code>${esc(RS.score_file)}</code>`],
    ["Produced by", `run <code>${esc(RS.run_id)}</code> (${esc(human(RS.run_status))}), recorded ${esc(String(RS.run_recorded_utc || "").replace("T", " ").slice(0, 16))} UTC; ${esc(RS.baseline_lineage || "")}`],
    ["Score", esc(RS.primary_score)], ["Rank convention", esc(RS.rank_convention || "")], ["Missing data", esc(RS.missing_policy)],
    ["Cohort", `${esc(C.n)} compounds: ${esc(C.positives)} with the outcome, ${esc(C.negatives)} without (${esc(C.label_definition || "")})`],
    ["Cutoff", esc(RS.cutoff)],
    ["Evaluation", `report ${esc(E.report_version || "")}, ordinary bootstrap seed ${esc(E.seed)}, ${esc(E.n_boot)} draws; run <code>${esc(E.run_id || "")}</code>`],
    ["Verification", `${RS.independent_recomputation ? '<span class="ok">✓</span> independent recomputation matched' : '<span class="bad">✕</span> independent recomputation not recorded'}; ${RS.all_files_match ? `<span class="ok">✓</span> all ${esc(arr(RS.files).length)} recorded files match their fingerprints` : '<span class="bad">✕</span> a recorded file changed'}; ${RS.code_fingerprint_recorded ? "code fingerprinted" : '<span class="warn">!</span> code version not fingerprinted (recorded before code fingerprints existed)'}`],
    ["Not verifiable", arr(RS.unfingerprinted).length ? arr(RS.unfingerprinted).map(u => `<span class="warn">!</span> ${esc(u.stage === "eval" ? "evaluation report" : u.stage)} reads <code>${esc(u.files)}</code>, not fingerprinted`).join("<br>") : "nothing"]];
  return `<div class="tablewrap"><table class="kv"><tbody>${rows.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td class="small">${v}</td></tr>`).join("")}</tbody></table></div>
    <details class="small"><summary>File fingerprints (${esc(arr(RS.files).length)})</summary>${table(arr(RS.files).map(f => ({role: f.role, file: f.path, "recorded md5": String(f.md5_recorded || "").slice(0, 12), matches: f.matches ? "yes" : "NO"})))}</details>`;
}
// Unapproved alternative result sets (e.g. the corrected molecular rule, TD-042): shown beside, never instead of, the
// approved result. Numbers come from the candidate's persisted comparison (same cohort, labels and bootstrap).
const ALT_LABEL = {td042_v1: "Corrected molecular rule"};
function alternativesPanel(A) {
  if (!A || A.__error) return errBox((A || {}).__error || "alternatives unavailable");
  const list = arr(A.alternatives);
  if (!list.length) return '<div class="empty">No alternative result set has a persisted comparison.</div>';
  return list.map(x => {
    const label = ALT_LABEL[x.name] || "Alternative result set";
    const head = `<div class="banner b-warn" role="note"><strong>Not approved.</strong> ${esc(label)}${x.decision ? ` — owner decision pending` : ""}. The approved result above is unchanged; this variant is shown for comparison only.</div>
      <p class="small"><strong>What it changes:</strong> ${esc(x.rule || "")}</p>`;
    const prov = provBox(`<code>${esc(x.source)}</code> · result set <code>${esc(x.name)}</code>${x.decision ? ` · decision ${esc(x.decision)}` : ""} · computed ${esc(x.generated_utc || "")} · independent verification ${x.independently_verified ? "passed" : "not recorded"} · ${esc(((x.procedure || {}).ci) || "")}`);
    if (x.withheld) return head + `<div class="banner b-bad">Comparison withheld: ${esc(x.withheld)}.</div>` + prov;
    const M = x.metrics || {}, P = x.paired || {}, C = x.cohort || {};
    const pd = (k, lab) => P[k] ? {label: lab, value: P[k].diff, ci: P[k].ci95} : null;
    const movers = arr(x.ranks).filter(r => r.rank_approved !== r.rank_candidate).sort((a, b) => Math.abs(b.rank_candidate - b.rank_approved) - Math.abs(a.rank_candidate - a.rank_approved));
    return head + `<div class="small">Same ${esc(C.n)} compounds and the same labels (${esc(C.positives)} with the outcome). Changed dimension ranks: ${Object.entries(x.dimensions_changed || {}).filter(([, n]) => n).map(([k, n]) => `${esc(DIM_NAME[k.replace(/^r_/, "")] || k)} ${esc(n)} compounds`).join(", ") || "none"}; top-10 overlap ${esc(x.top10_overlap)} of 10.</div>
      ${chartIntervals([{label: "Approved, 5 dimensions", value: (M.approved_5d || {}).auroc, ci: (M.approved_5d || {}).auroc_ci95},
                        {label: `${label}, 5 dimensions`, value: (M.candidate_5d || {}).auroc, ci: (M.candidate_5d || {}).auroc_ci95, cls: "alt"},
                        {label: "4 dimensions (no molecular)", value: (M.approved_4d || {}).auroc, ci: (M.approved_4d || {}).auroc_ci95}],
        {min: 0.3, max: 1, ticks: [0.3, 0.5, 0.7, 0.9, 1], ref: 0.5, refLabel: "chance", title: "AUROC with 95% bootstrap intervals, approved vs alternative", xLabel: "AUROC", caption: "Same cohort, labels and bootstrap procedure as the approved evaluation."})}
      ${chartIntervals([pd("approved_minus_candidate", "Approved minus alternative"), pd("candidate_minus_4d", "Alternative minus 4 dimensions")].filter(Boolean),
        {min: -0.15, max: 0.25, ticks: [-0.1, 0, 0.1, 0.2], ref: 0, refLabel: "no difference", title: "Paired AUROC differences", xLabel: "AUROC difference",
         caption: `Approved minus alternative: interval ${(P.approved_minus_candidate || {}).ci95 && P.approved_minus_candidate.ci95[0] > 0 ? "excludes" : "includes"} zero. Alternative minus 4 dimensions: interval ${(P.candidate_minus_4d || {}).ci95 && P.candidate_minus_4d.ci95[0] <= 0 && P.candidate_minus_4d.ci95[1] >= 0 ? "includes" : "excludes"} zero.`})}
      <p class="small">Interpretation: under this rule the 5-dimension score performs like the 4-dimension score, so the approved score's advantage over 4 dimensions depends on the rule being decided. AUPRC: approved ${esc(fmtN((M.approved_5d || {}).auprc))} vs alternative ${esc(fmtN((M.candidate_5d || {}).auprc))} (chance ${esc(fmtN(C.positives / C.n))}).</p>
      <details><summary>Rank changes (${esc(movers.length)} compounds move)</summary>${table(movers.slice(0, 40).map(r => ({compound: r.compound, outcome: r.label ? "new trial after 2020" : "none", "rank approved": r.rank_approved, "rank alternative": r.rank_candidate, "molecular approved": r.molecular_approved, "molecular alternative": r.molecular_candidate})))}</details>
      ${prov}`;
  }).join("<hr>");
}
function validationCharts(VC) {
  const bad = errBox((VC || {}).__error || (VC || {}).error || "validation charts unavailable");
  if (!VC || VC.__error || VC.error) return {perf: bad, baselines: "", ablation: "", missing: "", tech: ""};
  const prev = VC.prevalence, P = VC.paired_5d_vs_4d || {}, ab = (VC.ablation || {}).rows || {}, md = VC.missing_by_dimension || {}, im = VC.imputed_by_dimension || {};
  const dims = ["proximity", "clinical", "literature", "safety", "molecular"];
  return {
    perf: (VC.matches_report ? `<div class="grid2">${chartCurve([{label: "ROC, 5-dimension score", points: VC.roc}], {title: `ROC curve (AUROC ${fmtN(VC.auroc_recomputed)})`, xLabel: "false positive rate", yLabel: "true positive rate", diagonal: true, caption: "Diagonal = chance (AUROC 0.5). Steps are the 90 compounds' score thresholds."})}
      ${chartCurve([{label: "Precision-recall, 5-dimension score", points: VC.pr}], {title: `Precision-recall (AUPRC ${fmtN(VC.auprc_recomputed)})`, xLabel: "recall", yLabel: "precision", hline: prev, hlineLabel: "chance = prevalence", caption: "Dashed line = prevalence, the precision of a random ranking."})}</div>`
      : `<div class="banner b-bad">Curves unavailable: recomputing them from the approved scores did not reproduce the approved report (AUROC ${fmtN(VC.auroc_recomputed)}), so no curve is drawn.</div>`)
      + `<h3>Model comparison ${evalTag("unfitted")}</h3>`
      + chartIntervals(arr(VC.models).map(m => ({label: modelName(m.model), value: m.auroc, ci: m.ci95})), {min: 0.3, max: 1, ticks: [0.3, 0.5, 0.7, 0.9, 1], ref: 0.5, refLabel: "chance", title: "AUROC with 95% bootstrap intervals", xLabel: "AUROC", caption: "No weights were tuned on these labels for any of these models."})
      + (P.diff != null ? chartIntervals([{label: "5 dimensions minus 4 dimensions", value: P.diff, ci: P.ci95}], {min: -0.1, max: 0.25, ticks: [-0.1, 0, 0.1, 0.2], ref: 0, refLabel: "no difference", title: "Paired AUROC difference, 5 vs 4 dimensions", xLabel: "AUROC difference", caption: `The interval includes zero: the added value of the molecular dimension is not statistically supported (share of bootstrap draws above zero ${fmtN(P.p_diff_gt_0, 2)}).`}) : ""),
    baselines: chartBars([...arr(VC.models).map(m => ({label: modelName(m.model), value: m.auroc, text: fmtN(m.auroc), cls: /5d/.test(m.model) ? "pos" : ""})),
        ...Object.entries(VC.baselines || {}).map(([k, v]) => ({label: k, value: v, text: fmtN(v), note: "simple baseline from the approved report"}))].sort((a, b) => b.value - a.value),
      {title: "AUROC of the approved score and simple baselines", max: 1, left: 280, xLabel: "AUROC (0.5 = chance)", caption: "All unfitted. Baseline values are copied from the approved evaluation report (no intervals recorded for them)."}),
    ablation: chartBars(Object.entries(ab).map(([k, v]) => /grid/i.test(k) ? ({label: "All 5 (tuned weights, in-sample)", value: v, text: fmtN(v), cls: "insample", note: "weights chosen on these labels: optimistic, not comparable"}) : ({label: k.replace("Full VPS", "All 5"), value: v, text: fmtN(v), note: "equal weights over the remaining four dimensions"})), {title: "AUROC after removing one dimension", max: 1, left: 280, xLabel: "AUROC", caption: "Hatched bar: in-sample reference (weights tuned on these labels). Other bars: equal weights over the remaining dimensions."}),
    missing: chartBars(dims.map(d => ({label: DIM_NAME[d], value: (md[d] || 0) + (im[d] || 0), text: md[d] ? `${md[d]} not measured` : im[d] ? `${im[d]} median-imputed` : "complete", note: md[d] ? "assigned the neutral rank 0.5" : im[d] ? (im.proximity_compounds || []).join(", ") : ""})), {title: "Compounds without a measured value, per dimension", max: VC.n, left: 170, xLabel: `compounds (of ${VC.n})`, caption: "Not measured = no FDA label (safety) or no known drug target (molecular): neutral rank, not a penalty. Imputed = raw value missing, replaced by the pool median."}),
    imputation: arr(VC.imputation_paths),
    tech: `<details class="small"><summary>Technical details: curve recomputation</summary>Curves recomputed from <code>${esc(VC.source)}</code>; recomputed AUROC ${fmtN(VC.auroc_recomputed, 6)} and AUPRC ${fmtN(VC.auprc_recomputed, 6)} ${VC.matches_report ? "match" : "do not match"} the approved report. ${esc(VC.grid_search_note || "")}</details>`};
}
async function viewValidation() {
  const [v, o, ev, VC, L, ALT, RS] = await Promise.all([api("/api/validation"), api("/api/overview"), api("/api/evaluation"), api("/api/validation_charts"), api("/api/live"), api("/api/alternatives"), api("/api/result_set")]); if (v.__error) return errBox(v.__error);
  const r3 = x => typeof x === "number" ? x.toFixed(3) : "—", G = validationCharts(VC);
  const CI = (o && !o.__error && o.primary_ci) || {}, C = (o && o.cohort) || {}, okEv = !(ev.__error || ev.status);
  const prim = arr(ev.primary), p5 = prim.find(p => /5d/.test(p.model)) || {}, cv = okEv ? ((ev.grid_search || {}).repeated_nested_cv || {}) : {};
  const B3 = arr(((L || {}).science || {}).open_decisions).find(d => d.id === "B-003");
  const mt = (t, title, tag) => { t = t || {}; return `<h3>${esc(title)} ${tag || ""}</h3>${t.status ? `<div class="bad small">${esc(t.status)}</div>` : table(t.rows)}${provBox(`<code>${esc(t.source)}</code>${t.modified ? " · modified " + esc(t.modified) : ""}`)}`; };
  const I = v.integrity || {}, H = v.historical || {};
  const sec = (id, n, title, body) => `<section class="panel" id="v-${id}" aria-labelledby="h-${id}"><h2 id="h-${id}">${n}. ${esc(title)}</h2>${body}</section>`;
  const toc = [["perf", "Performance"], ["design", "Evaluation design"], ["base", "Baselines and ablations"], ["miss", "Missing and imputed data"], ["repro", "Reproducibility"], ["limits", "Methods and limitations"], ["alt", "Alternative scoring (not approved)"]];
  const summary = `<section class="panel intro"><h2>How the ranking was validated</h2>
    <ul class="plain checks small">
      <li><strong>Design:</strong> retrospective temporal check. Evidence is taken from before 2021; the outcome is whether a drug entered a new Parkinson's interventional trial first posted on or after 1 January 2021 (continued clinical investigation, <em>not efficacy</em>).</li>
      <li><strong>Cohort:</strong> ${fmt(C.compounds)} drugs with an earlier Parkinson's trial: ${fmt(C.positives)} with the outcome, ${fmt(C.negatives)} without (prevalence ${r3((ev.cohort || {}).prevalence)}).</li>
      <li><strong>Approved result:</strong> AUROC ${r3(p5.auroc)} (95% CI ${r3((p5.auroc_ci95 || [])[0])}–${r3((p5.auroc_ci95 || [])[1])}), AUPRC ${r3(p5.auprc)} against a chance level of ${r3((ev.cohort || {}).prevalence)} ${evalTag("unfitted")}.</li>
      <li><strong>Against baselines:</strong> above every simple baseline in the report (best ${r3(Math.max(...Object.values((VC || {}).baselines || {0: 0})))}); adding the molecular dimension is not shown to help (paired difference interval includes zero).</li>
      ${(() => { const x = arr((ALT || {}).alternatives).find(a => !a.withheld && a.metrics); return x ? `<li><strong>Open methodological question:</strong> a corrected molecular rule (not approved) gives AUROC ${r3(x.metrics.candidate_5d.auroc)} instead of ${r3(x.metrics.approved_5d.auroc)}, equal to the 4-dimension score; see section 7.</li>` : ""; })()}
      <li><strong>Missing data:</strong> ${Object.entries((VC || {}).missing_by_dimension || {}).filter(([, n]) => n).map(([k, n]) => `${esc(n)} without ${esc(DIM_NAME[k] || k)}`).join(", ")}${((VC || {}).imputed_by_dimension || {}).proximity ? `, ${esc(VC.imputed_by_dimension.proximity)} with imputed network proximity` : ""}.</li>
      <li><strong>Main limitations:</strong> only ${fmt(C.positives)} positives, so intervals are wide; no separate held-out cohort; literature, safety and molecular evidence are current snapshots, so the check is not leakage-free; ${B3 ? "a rerun from source gives a slightly different AUROC (reproducibility question open with the owner)" : "see Reproducibility"}.</li></ul>
    <nav class="toc small" aria-label="Validation sections">${toc.map(([id, l], k) => `<a href="#validation" data-jump="v-${id}">${k + 1}. ${esc(l)}</a>`).join("")}</nav></section>`;
  const performance = sec("perf", 1, "Performance", `<p class="small">${esc(VC.n)} compounds, ${esc(VC.positives)} with the outcome. All estimates use the same 90 compounds; there is no separate held-out cohort. With 14 positives the intervals are wide.</p>` + G.perf + G.tech);
  const design = sec("design", 2, "Evaluation design", `<ul class="small">
      <li><strong>Candidates.</strong> Hetionet v1.0 compounds linked to Parkinson's disease, excluding vitamins, electrolytes and basic metabolites; only drugs with an accepted Parkinson's interventional trial first posted before 2021-01-01 are evaluable (${fmt(C.compounds)}).</li>
      <li><strong>Outcome.</strong> ${esc(plainText(String((o || {}).endpoint || "").replace(/,?\s*excluding data\/label_role_exclusions\.csv/, "")))} Trials in which the drug serves a procedure, is only a comparator or actuates another therapy are excluded.</li>
      <li><strong>Evidence dimensions.</strong> Network proximity (Hetionet 2017), clinical maturity (highest pre-2021 trial phase), literature independence (PubMed co-authorship and citation clusters), FDA-label safety, molecular plausibility (ChEMBL targets → Open Targets association and Reactome pathways, with outcome-leaking data types excluded). Each becomes a percentile rank; the score is their equal-weight mean.</li>
      <li><strong>Cutoffs.</strong> Clinical evidence: trials first posted before 2021-01-01. Outcome: ClinicalTrials.gov snapshot queried 2026-10-05.</li>
      <li><strong>Statistics.</strong> AUROC and AUPRC with percentile-bootstrap 95% intervals (2,000 resamples, seed 42); paired bootstrap for model differences; tuned weights judged only on held-out folds. No calibration: the score is a rank, not a probability.</li></ul>
    <h3>Primary analysis ${evalTag("unfitted")}</h3>
    ${CI.status ? `<div class="bad">${esc(CI.status)}</div>` : `<div class="tablewrap"><table><thead><tr><th scope="col">estimate</th><th scope="col">evaluation type</th><th scope="col">AUROC</th><th scope="col">95% CI</th></tr></thead><tbody>
      <tr><td>${esc(CI.a)}</td><td>${evalTag("unfitted")}</td><td>${fmt(CI.auroc_a)}</td><td>${esc(pct(CI.ci_a_low, CI.ci_a_high))}</td></tr>
      <tr><td>${esc(CI.b)}</td><td>${evalTag("exploratory")}</td><td>${fmt(CI.auroc_b)}</td><td>${esc(pct(CI.ci_b_low, CI.ci_b_high))}</td></tr>
      <tr><td>paired 5d − 4d</td><td>bootstrap difference</td><td>${fmt(CI.diff)}</td><td>${esc(pct(CI.ci_diff_low, CI.ci_diff_high))} ${sigVerdict(CI.ci_diff_low, CI.ci_diff_high)}</td></tr></tbody></table></div>`}
    <div class="legend small">${Object.keys(EVAL_TYPE).map(k => `${evalTag(k)} ${esc(EVAL_TYPE[k])}`).join("<br>")}</div>`);
  const baselines = sec("base", 3, "Baselines and ablations", `<h3>Approved score versus simple baselines ${evalTag("unfitted")}</h3>${G.baselines}
    <h3>Removing one dimension</h3>${G.ablation}
    ${okEv ? `<h3>Tuned weights, judged on held-out folds ${evalTag("heldout")}</h3><div class="small muted">${esc(ev.grid_search.note)}</div>
      ${table(Object.entries(cv).map(([k, x]) => ({model: k, "mean held-out AUROC (20 splits)": x.mean, "2.5%": x.p2_5, "97.5%": x.p97_5})))}
      <div class="small">Tuned weights do not beat the unfitted equal weights on held-out data (5 dimensions: ${r3((cv["5d"] || {}).mean)} versus ${r3(p5.auroc)}).</div>` : ""}
    <details><summary>All score variants, baselines and ablation tables</summary>
      <div class="small muted">Rows with tuned weights report an in-sample AUROC ${evalTag("insample")}; use the held-out column as their performance estimate.</div>
      ${mt(v.variants, "Score variants", "")}${mt(v.baselines, "Baselines", evalTag("unfitted"))}${mt(v.ablation_4d, "Ablation, 4 dimensions", "")}${mt(v.ablation_5d, "Ablation, 5 dimensions", "")}</details>`);
  const missing = sec("miss", 4, "Missing and imputed data", G.missing + `<ul class="small">${arr(G.imputation).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    ${okEv ? `<div class="small">Positives among compounds with a missing dimension: ${fmt(ev.missing_data.positives_among_missing)}.</div>` : ""}
    <div class="small muted">Missing evidence is never read as negative evidence: an unmeasured dimension gets the neutral rank 0.5.</div>`);
  const repro = sec("repro", 5, "Reproducibility", `<p class="small">${RS && !RS.__error && !RS.status ? `${RS.all_files_match ? "All files of the approved result set still match the fingerprints recorded when it was produced" : '<span class="bad">A file of the approved result set changed since it was produced</span>'}; independent recomputation ${RS.independent_recomputation ? "matched" : "not recorded"}.` : ""}</p>
    <details><summary>Approved result set: data contract (files, run, cohort, cutoff, scoring version, fingerprints)</summary>${resultSetPanel(RS)}</details>` + (okEv ? `<ul class="small plain checks">
      <li>Inputs of the evaluation report: ${arr(ev.stale_inputs).length ? `<span class="bad">changed since the report was built (${ev.stale_inputs.map(esc).join(", ")})</span>` : '<span class="ok">unchanged since the report was built</span>'}.</li>
      <li>Bootstrap re-run identical: ${esc(ev.paired_5d_vs_4d.rerun_identical)} · matches the saved interval file: ${esc(ev.paired_5d_vs_4d.matches_persisted_ci_file)}.</li>
      ${B3 ? `<li><span class="warn">Open question:</span> ${esc(B3.detail)}</li>` : ""}</ul>
    <h3>Saved AUROCs recomputed now</h3>${table(arr(ev.reproduction.rows).map(r => ({model: r.model, type: r.type, saved: r.persisted, recomputed: r.recomputed, match: r.match})))}
    <h3>Data integrity checks</h3>${I.status ? `<div class="bad">${esc(I.status)}</div>` : kv(Object.fromEntries(Object.entries(I).filter(([k]) => k !== "source")))}
    ${provBox(`<code>${esc(ev.source)}</code> · ${esc(ev.modified)} · ${esc(ev.report_version)} · seed ${esc(ev.seed)}, ${esc(ev.n_boot)} bootstrap resamples · integrity computed from <code>${esc(I.source)}</code>`)}` : errBox(ev.__error || ev.status)));
  const limits = sec("limits", 6, "Methods and limitations", `${okEv ? `<h3>Calibration</h3><div class="small">${esc(ev.calibration.reason)}</div>
      <h3>Temporal validity</h3><div class="small warn">${esc(ev.temporal_validity)}</div>
      ${ev.duplicate_evidence ? `<h3>Shared trials</h3><div class="small">${esc(ev.duplicate_evidence.feature_trials_shared_by_pool_compounds)} pre-2021 trials are credited to more than one candidate (${esc(arr(ev.duplicate_evidence.pool_compounds_affected).length)} candidates affected): ${esc(ev.duplicate_evidence.meaning)}.</div>` : ""}
      <h3>Correlation between dimensions (Spearman)</h3>${table(Object.entries(ev.dimension_spearman).map(([a, row]) => ({dimension: a.slice(2), ...Object.fromEntries(Object.entries(row).map(([b, x]) => [b.slice(2), x]))})))}` : ""}
    <div class="small warn">Only 14 positives: model comparisons are underpowered. The score without literature stays above chance; the best time-bounded dimensions alone do not.</div>
    <h3>${esc(String(H.label || "Historical results").replace(/\s*\([^)]*\)\s*$/, ""))}</h3>${provBox(esc(H.label || ""))}<ul class="small">${arr(H.items).map(i => `<li>${esc(i)}</li>`).join("")}</ul><div class="small warn">${esc(H.caveat || "")}</div>
    <details><summary>Saved figures (${arr(v.figures).length})</summary>${arr(v.figures).map(f => `<h3><code>${esc(f.path)}</code> <span class="small muted">${esc(f.modified)}</span></h3><img class="fig" loading="lazy" alt="Figure file ${esc(f.path)}" src="/figure/${encodeURIComponent(String(f.path).split("/").pop())}">`).join("") || '<div class="empty">No figures found.</div>'}</details>
    <details class="small"><summary>How to re-run the tests</summary><code>${esc((v.tests || {}).command)}</code><div class="muted">${esc((v.tests || {}).note)}</div></details>`);
  const alternatives = sec("alt", 7, "Alternative scoring variant (not approved)", alternativesPanel(ALT));
  const after = () => $main.querySelectorAll("a[data-jump]").forEach(a => a.addEventListener("click", e => { e.preventDefault(); const t = document.getElementById(a.dataset.jump); if (t) { t.scrollIntoView({block: "start"}); t.querySelector("h2").setAttribute("tabindex", "-1"); t.querySelector("h2").focus({preventScroll: true}); } }));
  return {html: summary + performance + design + baselines + missing + repro + limits + alternatives, after};
}

// ---------- live pipeline status (polls /api/status only; never triggers computation) ----------
// The server reports a data_version that changes when any registered output or the run manifest
// changes. When it changes, cached data is dropped and the current view re-rendered in place,
// so scores, rankings, candidate pages and comparisons always come from the same file version.
const POLL_MS = 4000, POLL_RUNNING_MS = 1500, POLL_HIDDEN_MS = 20000, POLL_MAX_BACKOFF_MS = 30000;
let liveVersion = null, pollFailures = 0, pollTimer = null, lastStatus = null, lastServerInstance = null;
const $run = document.getElementById("runstate"), $banner = document.getElementById("banner"), $refreshed = document.getElementById("refreshed");
let lastRefreshOk = null;
const utcTime = d => d.toISOString().slice(11, 19) + " UTC";     // every time in the app is UTC
function describeVps(v) {
  v = v || {};
  const d = describeVpsState(v);
  const failed = v.latest_attempt_failed && v.status !== "FAILED"
    ? `Latest VPS attempt FAILED (run ${(v.last_attempt || {}).run_id || "?"}). ` : "";
  const warn = arr(v.warnings).length ? ` Note: ${v.warnings.join("; ")}.` : "";
  if (!d && !failed && !warn) return null;
  return {level: failed ? "bad" : (d || {level: "warn"}).level, text: failed + (d ? d.text : "") + warn};
}
function describeVpsState(v) {
  const run = v.displayed_run_id ? ` (displayed result: run ${v.displayed_run_id})` : "";
  switch (v.status) {
    case "RUNNING": return {level: "info", text: `VPS is being recomputed (run ${(v.last_attempt || {}).run_id || "?"} started ${(v.last_attempt || {}).started_utc || "?"}). The page keeps showing the last validated result until the new one is published${run}.`};
    case "STALE": return {level: "warn", text: `VPS is STALE: ${(v.reasons || []).join("; ")}. The scores shown are the retained result${run}; recompute with ./venv/bin/python scripts/run_stage.py 06.`};
    case "MODIFIED": return {level: "bad", text: `VPS file changed outside a tracked run and has not been validated: ${(v.reasons || []).join("; ")}.`};
    case "FAILED": return {level: "bad", text: `Latest VPS attempt FAILED: ${(v.reasons || []).join("; ")}.${v.retained_run_id ? " Showing the retained result of run " + v.retained_run_id + " — not a fresh result." : " No valid VPS exists."}`};
    case "MISSING": return {level: "bad", text: `A published VPS file is missing: ${(v.reasons || []).join("; ")}. Scores cannot be shown as current; restore it or re-run ./venv/bin/python scripts/run_stage.py 06.`};
    case "UNTRACKED": case "NOT_RUN": return {level: "warn", text: `VPS has no tracked run (${v.status}).`};
    case "UNKNOWN": return {level: "bad", text: `VPS run state is UNKNOWN: ${(v.reasons || []).join("; ")}. The scores shown cannot be confirmed as current; check with ./venv/bin/python scripts/run_stage.py --check-manifest.`};
    default: return null;
  }
}
function renderLive(st) {
  lastStatus = st;
  const by = st.by_status || {}, bad = (by.ATTEMPT_FAILED || []).length, stale = (by.STALE || []).length + (by.MODIFIED || []).length + (by.MISSING || []).length;
  const running = by.RUNNING || [];
  // "current" only when every stage has a known, fresh state; unknown/untracked/never-run are not current
  const unknown = (by.UNKNOWN || []).length + (by.UNTRACKED || []).length + (by.NOT_RUN || []).length;
  $run.className = "runstate " + (st.manifest_error ? "rs-bad" : running.length ? "rs-run" : bad ? "rs-bad" : stale || unknown || (by.UNVERIFIABLE || []).length ? "rs-warn" : "rs-ok");
  $run.textContent = st.manifest_error ? "Run records unreadable" : running.length ? `Running: ${running.join(", ")}` : bad ? `${bad} stage(s) failed` : stale ? `${stale} stage(s) stale` : unknown ? `${unknown} stage(s) without a known run state` : (by.UNVERIFIABLE || []).length ? "Current against recorded inputs — some inputs not verifiable" : "Current against recorded inputs";
  $run.title = `VPS ${st.vps.status}${st.vps.displayed_run_id ? " · run " + st.vps.displayed_run_id : ""} · checked ${st.server_time_utc}`;
  const d = st.server_code_changed
    ? {level: "warn", text: "The dashboard server is running older code than the files on disk, so some pages may not match the server. Restart it: stop the server and run ./venv/bin/python ui/server.py."}
    : describeVps(st.vps);
  if (d) { $banner.hidden = false; $banner.className = "banner b-" + d.level; $banner.textContent = d.text; }
  else { $banner.hidden = true; $banner.textContent = ""; }
}
// One poll at a time: a second concurrent poll (e.g. the tab becoming visible while a poll or the re-render it
// triggered is still running) could let an older response render over a newer one. Requests made meanwhile are
// coalesced into one immediate follow-up.
let pollInFlight = false, pollAgain = false;
async function poll() {
  if (pollInFlight) { pollAgain = true; return; }
  pollInFlight = true;
  try { await pollOnce(); }
  finally {                    // an unexpected error in a render must not end live updates
    pollInFlight = false;
    clearTimeout(pollTimer);
    const active = liveLaunchActive || arr((lastStatus || {}).stages).some(x => x.status === "RUNNING");
    const wait = pollAgain ? 0 : pollFailures ? Math.min(POLL_MS * 2 ** pollFailures, POLL_MAX_BACKOFF_MS) : (document.hidden ? POLL_HIDDEN_MS : active ? POLL_RUNNING_MS : POLL_MS);
    pollAgain = false;
    pollTimer = setTimeout(poll, wait);
  }
}
async function pollOnce() {
  const st = await api("/api/status");
  if (st.__error) {
    pollFailures++;
    $refreshed.textContent = lastRefreshOk ? `Server not responding — last update ${utcTime(lastRefreshOk)}` : "Server not responding";
    $refreshed.className = "small bad";
    $run.className = "runstate rs-bad";
    $run.textContent = "Connection to the local server lost — retrying";
    $run.title = st.__error;
  } else {
    const recovered = pollFailures > 0;
    pollFailures = 0;
    lastRefreshOk = new Date();
    $refreshed.textContent = `Updated ${utcTime(lastRefreshOk)}`;
    $refreshed.className = "small muted";
    if (st.server_instance !== lastServerInstance) { liveSession = null; lastServerInstance = st.server_instance; }   // new server: new nonce
    renderLive(st);
    if (liveVersion !== null && st.data_version !== liveVersion) {
      liveVersion = st.data_version;
      compoundsCache = rankingCache = null;
      await route({keepScroll: true, reason: "data updated"});
    } else {
      liveVersion = st.data_version;
      if (recovered || LIVE_VIEWS.has(parseHash().view)) await route({keepScroll: true, reason: recovered ? "reconnected" : "live"});
    }
  }
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) { clearTimeout(pollTimer); poll(); }      // refresh immediately when the tab returns
});


// ---------- charts: small dependency-free SVG from real API data; every chart carries a data-table alternative ----------
const fmtN = (v, d = 3) => v == null || !isFinite(v) ? "—" : Number(v).toFixed(d);
function dataTable(caption, head, rows) {
  return `<details class="small chartdata"><summary>Data table: ${esc(caption)}</summary><div class="tablewrap"><table><thead><tr>${head.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}
// Point estimates with 95% intervals on a shared axis, optional reference line (e.g. chance or zero).
function chartIntervals(items, o) {
  const W = 640, rowH = 26, left = 230, right = 70, top = 22, H = top + items.length * rowH + 30;
  const lo = o.min, hi = o.max, x = v => left + (W - left - right) * (v - lo) / (hi - lo);
  const ticks = o.ticks || [lo, (lo + hi) / 2, hi];
  return `<figure class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    ${ticks.map(t => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top - 6}" y2="${H - 26}"/><text class="tick" x="${x(t)}" y="${H - 10}" text-anchor="middle">${esc(fmtN(t, 2))}</text>`).join("")}
    ${o.ref != null ? `<line class="ref" x1="${x(o.ref)}" x2="${x(o.ref)}" y1="${top - 10}" y2="${H - 26}"/><text class="reflabel" x="${x(o.ref) + 4}" y="${top - 10}">${esc(o.refLabel || "")}</text>` : ""}
    ${items.map((it, i) => { const y = top + i * rowH + rowH / 2; const ci = it.ci || [];
      return `<g><text class="lab" x="${left - 8}" y="${y + 4}" text-anchor="end">${esc(it.label)}</text>
        ${ci.length === 2 ? `<line class="ci" x1="${x(Math.max(lo, ci[0]))}" x2="${x(Math.min(hi, ci[1]))}" y1="${y}" y2="${y}"/>` : ""}
        <circle class="pt ${it.cls || ""}" cx="${x(it.value)}" cy="${y}" r="5"><title>${esc(it.label)}: ${esc(fmtN(it.value))}${ci.length === 2 ? ` (95% CI ${fmtN(ci[0])} to ${fmtN(ci[1])})` : ""}</title></circle>
        <text class="val" x="${W - right + 6}" y="${y + 4}">${esc(fmtN(it.value))}</text></g>`; }).join("")}
    <text class="axis" x="${left + (W - left - right) / 2}" y="${H}" text-anchor="middle">${esc(o.xLabel || "")}</text></svg>
    <figcaption class="small muted">${esc(o.caption || "")}</figcaption>
    ${dataTable(o.title, ["item", "value", "95% interval"], items.map(it => [it.label, fmtN(it.value), it.ci ? `${fmtN(it.ci[0])} to ${fmtN(it.ci[1])}` : "—"]))}</figure>`;
}
// Horizontal bars (value 0..max); items may carry a marker class and a note shown in the tooltip.
function chartBars(items, o) {
  const W = 640, rowH = o.rowH || 20, left = o.left || 170, right = 60, top = 8, H = top + items.length * rowH + 26;
  const max = o.max || Math.max(1, ...items.map(i => i.value || 0)), x = v => (W - left - right) * (v || 0) / max;
  return `<figure class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    <defs><pattern id="hatchb" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="hatchline"/></pattern></defs>
    ${items.map((it, i) => { const y = top + i * rowH;
      return `<g class="bar ${it.cls || ""}"${it.key ? ` data-key="${esc(it.key)}" tabindex="0" role="button" aria-label="${esc(it.label)}: ${esc(it.text || fmtN(it.value))}"` : ""}>
        <text class="lab" x="${left - 6}" y="${y + rowH * 0.7}" text-anchor="end">${esc(it.label)}</text>
        <rect x="${left}" y="${y + 3}" width="${Math.max(1, x(it.value))}" height="${rowH - 6}" rx="2"><title>${esc(it.label)}: ${esc(it.text || fmtN(it.value))}${it.note ? " — " + esc(it.note) : ""}</title></rect>
        <text class="val" x="${left + x(it.value) + 4}" y="${y + rowH * 0.7}">${esc(it.text || fmtN(it.value))}${it.mark ? " " + esc(it.mark) : ""}</text></g>`; }).join("")}
    <text class="axis" x="${left + (W - left - right) / 2}" y="${H - 4}" text-anchor="middle">${esc(o.xLabel || "")}</text></svg>
    <figcaption class="small muted">${esc(o.caption || "")}</figcaption>
    ${o.noTable ? "" : dataTable(o.title, ["item", "value", "note"], items.map(it => [it.label, it.text || fmtN(it.value), it.note || ""]))}</figure>`;
}
// Step curve(s) on the unit square (ROC / precision-recall).
function chartCurve(series, o) {
  const W = 320, H = 300, L = 46, B = 40, T = 12, R = 12, x = v => L + (W - L - R) * v, y = v => H - B - (H - B - T) * v;
  return `<figure class="chart curve"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    ${[0, .25, .5, .75, 1].map(t => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${y(0)}" y2="${y(1)}"/><line class="grid" x1="${x(0)}" x2="${x(1)}" y1="${y(t)}" y2="${y(t)}"/><text class="tick" x="${x(t)}" y="${H - B + 14}" text-anchor="middle">${t}</text><text class="tick" x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}
    ${o.diagonal ? `<line class="ref" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/>` : ""}
    ${o.hline != null ? `<line class="ref" x1="${x(0)}" y1="${y(o.hline)}" x2="${x(1)}" y2="${y(o.hline)}"/><text class="reflabel" x="${x(1) - 4}" y="${y(o.hline) - 4}" text-anchor="end">${esc(o.hlineLabel || "")}</text>` : ""}
    ${series.map(sr => `<polyline class="line" points="${sr.points.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")}"><title>${esc(sr.label)}</title></polyline>`).join("")}
    <text class="axis" x="${L + (W - L - R) / 2}" y="${H - 6}" text-anchor="middle">${esc(o.xLabel)}</text>
    <text class="axis" transform="translate(12 ${(H - B) / 2}) rotate(-90)" text-anchor="middle">${esc(o.yLabel)}</text></svg>
    <figcaption class="small muted">${esc(o.caption || "")}</figcaption>
    ${dataTable(o.title, [o.xLabel, o.yLabel], series[0].points.map(p => [fmtN(p[0]), fmtN(p[1])]))}</figure>`;
}
// Layered dependency graph: columns = dependency depth, arrows = "is an input to". Status shown by text and colour.
// Short state names that fit a graph box; the full label stays in the tooltip and the data table.
const SHORT_STATE = {SUCCESS: "Completed", ADOPTED: "Baseline", STALE: "Inputs changed", FAILED: "Failed", RUNNING: "Running",
  NOT_RUN: "Not run", PARTIAL: "With gaps", UNKNOWN: "Unknown", MODIFIED: "Edited", MISSING: "Missing", UNTRACKED: "Untracked"};
function chartDag(stages, o) {
  const cols = {}; stages.forEach(s => (cols[s.depth] = cols[s.depth] || []).push(s));
  const depths = Object.keys(cols).map(Number).sort((a, b) => a - b), w = 104, h = 36, gx = 40, gy = 12;
  const pos = {}; depths.forEach((d, ci) => cols[d].forEach((s, ri) => { pos[s.id] = {x: 8 + ci * (w + gx), y: 8 + ri * (h + gy)}; }));
  const W = 16 + depths.length * (w + gx) - gx, H = 16 + Math.max(...depths.map(d => cols[d].length)) * (h + gy) - gy;
  const edges = stages.flatMap(s => (s.upstream || []).filter(u => pos[u]).map(u => {
    const a = pos[u], b = pos[s.id], x1 = a.x + w, y1 = a.y + h / 2, x2 = b.x - 3, y2 = b.y + h / 2, mx = (x1 + x2) / 2;
    return `<path class="edge" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" marker-end="url(#arr)"/>`; }));
  return `<figure class="chart dag"><div class="dagwrap"><svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="arrowhead"/></marker></defs>
    ${edges.join("")}
    ${stages.map(s => { const p = pos[s.id]; const st = s.latest_attempt_failed && s.status !== "RUNNING" ? "FAILED" : s.status;
      return `<g class="node st-${esc(st)}"${o.link ? ` data-stage="${esc(s.id)}"` : ""}><rect x="${p.x}" y="${p.y}" width="${w}" height="${h}" rx="5"/>
        <text x="${p.x + w / 2}" y="${p.y + 14}" text-anchor="middle" class="nid">${esc(s.id)}</text>
        <text x="${p.x + w / 2}" y="${p.y + 28}" text-anchor="middle" class="nst">${esc(SHORT_STATE[st] || human(st))}</text>
        <title>${esc(s.id + " · " + s.name + " · " + human(st) + (s.reasons && s.reasons.length ? " · " + s.reasons.join("; ") : ""))}</title></g>`; }).join("")}
    </svg></div><figcaption class="small muted">${esc(o.caption || "")}</figcaption>
    ${dataTable(o.title, ["stage", "name", "state", "depends on"], stages.map(s => [s.id, s.name, human(s.latest_attempt_failed && s.status !== "RUNNING" ? "FAILED" : s.status), (s.upstream || []).join(", ") || "—"]))}</figure>`;
}
// Recent runs on a time axis (bar = start to finish; very short runs get a minimum width).
function chartTimeline(runs, o) {
  const rs = runs.filter(r => r.started_utc).slice(0, o.n || 12).reverse();
  if (!rs.length) return '<div class="empty">No runs recorded yet. Runs appear here as soon as a stage is started.</div>';
  const t = s => Date.parse(s), t0 = Math.min(...rs.map(r => t(r.started_utc))), t1 = Math.max(...rs.map(r => t(r.finished_utc || r.started_utc)), t0 + 60000);
  const W = 640, left = 70, right = 110, rowH = 20, H = rowH * rs.length + 30, x = v => left + (W - left - right) * (v - t0) / (t1 - t0);
  return `<figure class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    ${rs.map((r, i) => { const y = 4 + i * rowH, a = x(t(r.started_utc)), b = Math.max(a + 4, x(t(r.finished_utc || r.started_utc)));
      return `<g class="run st-${esc(r.status)}"><text class="lab" x="${left - 6}" y="${y + 13}" text-anchor="end">${esc(r.stage)}</text><rect x="${a}" y="${y + 3}" width="${b - a}" height="${rowH - 7}" rx="2"><title>${esc(r.stage)} · ${esc(human(r.status))} · ${esc(dur(r.duration_s))} · started ${esc(r.started_utc)}</title></rect>
        <text class="val" x="${W - right + 6}" y="${y + 13}">${esc(human(r.status))}${r.duration_s != null ? " · " + esc(dur(r.duration_s)) : ""}</text></g>`; }).join("")}
    <text class="tick" x="${left}" y="${H - 6}">${esc(String(rs[0].started_utc).slice(0, 16).replace("T", " "))} UTC</text>
    <text class="tick" x="${W - right}" y="${H - 6}" text-anchor="end">${esc(new Date(t1).toISOString().slice(0, 16).replace("T", " "))} UTC</text></svg>
    <figcaption class="small muted">${esc(o.caption || "")}</figcaption>
    ${dataTable(o.title, ["run", "stage", "state", "duration", "started (UTC)"], rs.slice().reverse().map(r => [r.run_id, r.stage, human(r.status), dur(r.duration_s), r.started_utc]))}</figure>`;
}
// Dimension ranks for one or more candidates (grouped bars). Missing = hatched + label; imputed = marked.
const DIM_LABEL = {proximity: "Network proximity", clinical: "Clinical", literature: "Literature", safety: "Safety", molecular: "Mechanism"};
function chartDims(cands, o) {
  const dims = ["proximity", "clinical", "literature", "safety", "molecular"], W = 640, left = 130, right = 20, gH = 14 * cands.length + 12;
  const H = dims.length * gH + 34, x = v => (W - left - right) * v;
  return `<figure class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title)}"><title>${esc(o.title)}</title>
    <defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="hatchline"/></pattern></defs>
    ${[0, .25, .5, .75, 1].map(t => `<line class="grid" x1="${left + x(t)}" x2="${left + x(t)}" y1="2" y2="${H - 28}"/><text class="tick" x="${left + x(t)}" y="${H - 14}" text-anchor="middle">${t}</text>`).join("")}
    ${dims.map((d, i) => `<text class="lab" x="${left - 8}" y="${i * gH + gH / 2 + 4}" text-anchor="end">${esc(DIM_LABEL[d])}</text>` + cands.map((c, k) => {
      const v = c[d], miss = String(c.dimensions_missing || "").split("|").includes(d), imp = String(c.dimensions_imputed || "").split("|").includes(d);
      const y = i * gH + 6 + k * 14;
      return `<rect class="series s${k}${miss ? " missing" : ""}" x="${left}" y="${y}" width="${Math.max(1, x(v || 0))}" height="11" rx="2"><title>${esc(c.compound)} · ${esc(d)}: ${miss ? "not measured — neutral rank 0.5 assigned" : fmtN(v)}${imp ? " (raw value missing; median-imputed)" : ""}</title></rect>${miss || imp ? `<text class="val" x="${left + x(v || 0) + 4}" y="${y + 10}">${miss ? "not measured (0.5)" : "imputed"}</text>` : ""}`; }).join("")).join("")}
    <text class="axis" x="${left + (W - left - right) / 2}" y="${H - 2}" text-anchor="middle">percentile rank within the 90-compound pool (higher = more favourable)</text></svg>
    <div class="legend small">${cands.map((c, k) => `<span><i class="sw s${k}"></i>${esc(c.compound)}</span>`).join(" ")} <span><i class="sw missing"></i>not measured (neutral 0.5)</span></div>
    ${dataTable(o.title, ["candidate", ...dims.map(d => DIM_LABEL[d])], cands.map(c => [c.compound, ...dims.map(d => String(c.dimensions_missing || "").split("|").includes(d) ? "not measured (0.5)" : fmtN(c[d]) + (String(c.dimensions_imputed || "").split("|").includes(d) ? " (imputed)" : ""))]))}</figure>`;
}

// ---------- Dashboard (default view): live application state from /api/live (run tracker = source of truth) ----------
const ago = iso => { if (!iso) return ""; const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  return s < 90 ? `${s} s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`; };
const hhmm = iso => iso ? esc(String(iso).slice(11, 19)) + " UTC" : "";
function liveActionButton(stageId, cls, busy, label) {
  if (cls === "REFUSED" || !cls) return "";
  if (busy) return `<button type="button" class="act" disabled>${esc(label || "Run")}</button>`;
  if (cls === "CONFIRM" && liveConfirm === stageId)
    return `<button type="button" class="act" data-run="${esc(stageId)}" data-confirm="1">Confirm run ${esc(stageId)}</button> <button type="button" class="act ghost" data-cancel-confirm="1">Back</button>`;
  return `<button type="button" class="act" data-run="${esc(stageId)}"${cls === "CONFIRM" ? ' data-ask="1"' : ""}>${esc(label || "Run")}${cls === "CONFIRM" ? "…" : ""}</button>`;
}
function bindLiveActions() {
  $main.querySelectorAll("button[data-run]").forEach(b => b.addEventListener("click", ev => {
    ev.preventDefault(); ev.stopPropagation();
    if (b.dataset.ask) { liveConfirm = b.dataset.run; route({keepScroll: true}); return; }
    livePost(b.dataset.confirm ? {stage: b.dataset.run, confirm: true} : {stage: b.dataset.run});
  }));
  $main.querySelectorAll("button[data-cancel-confirm]").forEach(b => b.addEventListener("click", ev => { ev.preventDefault(); liveConfirm = null; route({keepScroll: true}); }));
  $main.querySelectorAll("button[data-pipeline]").forEach(b => b.addEventListener("click", () => livePost({pipeline: true})));
}
// Per-stage outcome of a "run all" launch, from the runner's SEQUENCE line: ran / skipped (fresh) / failed / blocked.
function seqSummary(seq) {
  if (!Array.isArray(seq) || !seq.length) return "";
  const by = {};
  seq.forEach(r => (by[r.status] = by[r.status] || []).push(r.stage));
  const label = {SUCCESS: "ran", PARTIAL: "partial", SKIPPED_FRESH: "skipped (fresh)", FAILED: "failed", BLOCKED: "blocked by a failed prerequisite", REFUSED: "refused"};
  return `<div class="seq">${Object.entries(by).map(([k, v]) => `<span class="${k === "FAILED" || k === "BLOCKED" || k === "REFUSED" ? "bad" : k === "SKIPPED_FRESH" ? "muted" : "ok"}">${esc(label[k] || k)}: ${v.map(esc).join(", ")}</span>`).join(" · ")}</div>`;
}
const agentOfStage = (L, sid) => (arr(L.agents).find(a => arr(a.stages).includes(sid)) || {}).id || "";
async function viewDashboard() {
  const L = await api("/api/live");
  if (L.__error) return errBox(L.__error + " — the server could not report the pipeline state. Check that ./venv/bin/python ui/server.py is running.");
  const o = L.overall, F = L.freshness || {}, SC = L.science || {}, busy = o.running.length > 0 || L.launches.some(l => l.state === "RUNNING") || !!L.manifest_error;
  liveLaunchActive = L.launches.some(l => l.state === "RUNNING");
  const unv = arr(F.untracked_inputs).concat(arr(F.untracked_outputs));
  const headline = STATE_HEADLINE[o.state] || o.state;
  const tile = (n, label, cls, title) => `<div class="tile ${cls}" title="${esc(title)}"><div class="n">${esc(n)}</div><div class="l">${esc(label)}</div></div>`;
  const stById = Object.fromEntries(L.stages.map(x => [x.id, x]));
  const fb = liveFeedback ? `<div class="banner b-${esc(liveFeedback.level === "ok" ? "info" : liveFeedback.level)}" role="status">${esc(liveFeedback.text)}</div>` : "";
  const when = iso => iso ? `${esc(String(iso).slice(0, 16).replace("T", " "))} UTC <span class="muted">(${esc(ago(iso))})</span>` : '<span class="muted">not recorded</span>';
  const active = o.running.length ? o.running.map(id => { const x = stById[id] || {};
      return `<div class="activity"><span class="pulse" aria-hidden="true"></span><div><strong>${esc(x.name || id)}</strong> <span class="muted small">${esc(id)}</span>
        <div class="small">running for ${esc(dur(x.elapsed_s))}${x.last_attempt ? ` · run <code>${esc(x.last_attempt.run_id)}</code>` : ""}</div>
        <div class="small mono">${x.last_activity && x.last_activity.line ? "Latest log line: " + esc(x.last_activity.line) + ` <span class="muted">(${esc(dur(x.last_activity.log_age_s))} ago)</span>` : '<span class="muted">No log output yet.</span>'}</div></div></div>`; }).join("")
    : '<div class="small">No stage is running.</div>';
  const lastLaunch = L.launches[0];
  const agentCard = a => `<a class="agent s-card-${esc(a.status)}" href="#agent/${esc(a.id)}">
      <div class="agent-top"><span class="aname">${esc(a.name)}</span>${badge(a.running ? "RUNNING" : a.status)}${!a.running && a.latest_attempt_failed ? badge("FAILED") : ""}</div>
      <div class="small muted" title="agent ${esc(a.id)}">${esc(a.kind === "VPS input" ? "Checks a score input (does not change the score)" : a.kind === "annotation" ? "Annotation only" : "Diagnostic, not in the score")}</div>
      <div class="small cov">${esc(a.coverage_line)}</div>
      <div class="small">Output checks: ${a.output_envelope_valid === true ? '<span class="ok">passed</span>' : a.output_envelope_valid === false ? '<span class="bad">failed</span>' : '<span class="muted">output unavailable</span>'}${a.output_stale_inputs ? ` · <span class="warn">${esc(a.output_stale_inputs)} input(s) changed since</span>` : ""}</div>
      <div class="small muted">${a.running_activity ? `running ${esc(dur(a.running_activity[1]))}` : a.latest_attempt ? `Last run: ${esc(human(a.latest_attempt.status).replace(/^Run /, "").toLowerCase())} ${esc(ago(a.latest_attempt.finished_utc || a.latest_attempt.started_utc))}${a.latest_attempt.duration_s != null ? ", took " + esc(dur(a.latest_attempt.duration_s)) : ""}` : "No tracked run"}</div></a>`;
  const counts = {};
  L.stages.forEach(x => { const k = x.latest_attempt_failed && x.status !== "RUNNING" ? "FAILED" : x.status; counts[k] = (counts[k] || 0) + 1; });
  const pm = SC.primary_metric, coh = SC.cohort || {};
  const html = `<section class="hero st-${esc(o.state)}">
      <div class="hero-main"><div class="hero-label">Pipeline health</div><div class="hero-state">${esc(headline)}</div>
        <div class="small">Last successful run: ${when(F.last_success_utc)}</div>
        ${unv.length ? `<div class="small warn">${esc(unv.length)} stage file(s) were not fingerprinted at their last run, so changes to them cannot be detected (see Stage freshness).</div>` : ""}
        ${(F.code_unverifiable || []).length ? `<div class="small muted">Code changes cannot be detected for ${esc(F.code_unverifiable.length)} stages recorded before code fingerprints existed.</div>` : ""}
        ${L.manifest_error ? `<div class="small bad">${esc(L.manifest_error)}. Launches are disabled; diagnose with <code>./venv/bin/python scripts/run_stage.py --check-manifest</code>.</div>` : ""}</div>
      <div class="tiles">${tile(o.running.length, "running", o.running.length ? "t-run" : "", o.running.join(", ") || "none")}${tile(o.failed.length, "failed", o.failed.length ? "t-bad" : "", o.failed.join(", ") || "none")}${tile(o.stale.length, "inputs changed", o.stale.length ? "t-warn" : "", o.stale.join(", ") || "none")}${tile(o.unknown.length, "never run", o.unknown.length ? "t-warn" : "", o.unknown.join(", ") || "none")}${tile((o.counts.SUCCESS || 0) + (o.counts.ADOPTED || 0) + (o.counts.PARTIAL || 0), "current", "t-ok", "Run completed or recorded baseline, with unchanged tracked inputs")}</div>
      <div class="hero-act"><button type="button" class="act primary" data-pipeline="1"${busy ? " disabled" : ""}>Run all ${esc(L.n_allowed)} permitted stages</button>
        <div class="small muted">Runs in dependency order and skips stages whose inputs are unchanged. Stages that rewrite approved data never run from this screen. <a href="#live">All stages</a></div></div>
    </section>
    ${fb}
    <section class="panel next"><h2>Next step</h2><ul class="plain">${arr(L.next_actions).map(a => `<li class="na na-${esc(a.level)}"><span class="who">${esc(a.who === "anyone" ? "you" : a.who)}</span> ${a.stage ? `<a href="${agentOfStage(L, a.stage) ? "#agent/" + esc(agentOfStage(L, a.stage)) : "#live"}">${esc(a.text)}</a>` : esc(a.text)}</li>`).join("")}</ul></section>
    <h2 class="section-h">Is it up to date?</h2>
    <div class="grid2">
      <section class="panel"><h3>Runtime</h3>${active}
        ${lastLaunch ? `<div class="small">Latest launch from this screen: ${badge(lastLaunch.state === "EXITED" ? (lastLaunch.exit_code === 0 ? "SUCCESS" : "FAILED") : lastLaunch.state.split(" ")[0])} <code>${esc(lastLaunch.launch_id)}</code> · ${esc(ago(lastLaunch.finished_utc || lastLaunch.requested_utc))}${lastLaunch.exit_code != null ? " · exit code " + esc(lastLaunch.exit_code) : ""}${seqSummary(lastLaunch.sequence)}</div>` : '<div class="small muted">No run has been launched from this screen.</div>'}
        <div class="small muted">The header shows when this page last heard from the server.</div></section>
      <section class="panel"><h3>Stage freshness</h3>
        <div class="small">Freshness compares each stage's inputs and outputs with the fingerprints recorded at its last successful run; a file date alone never counts.</div>
        <ul class="small plain">
          <li>${(F.inputs_changed || []).length ? `<span class="warn">Inputs changed since the last run:</span> ${F.inputs_changed.map(esc).join(", ")}` : '<span class="ok">No tracked input has changed.</span>'}</li>
          ${arr(F.untracked_inputs).map(u => `<li><span class="warn">Not verifiable:</span> ${esc(u.name || u.stage)} reads <code>${esc(u.detail)}</code>, which was not fingerprinted at its last run, so a change to it would not be detected. ${u.rewrites_protected ? "Re-running it would rewrite approved research data, so this is the owner's decision." : "Re-running it records the fingerprint."}</li>`).join("")}
          ${arr(F.untracked_outputs).map(u => `<li><span class="warn">Not verifiable:</span> ${esc(u.name || u.stage)} writes <code>${esc(u.detail)}</code>, which was not fingerprinted at its last run, so an edit to it would not be detected.</li>`).join("")}
          ${(F.code_unverifiable || []).length ? `<li><span class="muted">Code changes not detectable for ${esc(F.code_unverifiable.length)} baseline stages</span> (${F.code_unverifiable.map(esc).join(", ")}): they were recorded before code fingerprints existed.</li>` : ""}
        </ul></section>
      <section class="panel"><h3>Source data</h3><div class="tablewrap"><table class="small"><thead><tr><th scope="col">source</th><th scope="col">retrieved</th><th scope="col">snapshot / cutoff</th></tr></thead><tbody>
        ${arr(L.sources).map(x => `<tr><td><strong>${esc(x.source)}</strong><div class="muted">${esc(x.what)}</div></td><td>${x.retrieved_utc ? when(x.retrieved_utc) : '<span class="muted">not recorded</span>'}</td><td>${esc(x.snapshot || (x.cutoff ? "cutoff " + x.cutoff : "—"))}<div class="muted">${esc(x.note || "")}</div></td></tr>`).join("")}</tbody></table></div></section>
      <section class="panel"><h3>Scientific validation</h3>
        <div class="small">Approved score: run <code>${esc(SC.approved_run_id || "none")}</code> · independent recomputation ${SC.independent_recomputation === true ? '<span class="ok">matches</span>' : SC.independent_recomputation === false ? '<span class="bad">does not match</span>' : '<span class="muted">not recorded</span>'}</div>
        <div class="small">Cohort: ${esc(coh.n)} candidate compounds · ${esc(coh.positives)} with continued Parkinson's trials after 2020 · ${esc(coh.negatives)} without</div>
        ${pm ? chartIntervals([{label: "AUROC (primary, 5 dimensions)", value: pm.value, ci: pm.ci95}, {label: "AUPRC (primary)", value: pm.auprc, ci: pm.auprc_ci95, cls: "alt"}], {min: 0, max: 1, ticks: [0, .25, .5, .75, 1], ref: 0.5, refLabel: "AUROC chance", title: "Primary evaluation with 95% bootstrap intervals", caption: `AUPRC chance level equals prevalence (${fmtN(coh.prevalence, 3)}). Approved result; not a probability of efficacy.`}) : ""}
        <div class="small"><strong>Open owner decisions</strong></div><ul class="small plain">${arr(SC.open_decisions).map(d => `<li title="${esc(d.id)}"><a href="${esc(d.href)}">${esc(d.title)}</a>: ${esc(d.detail)}</li>`).join("")}
          ${SC.reviews_awaiting ? `<li><a href="#review">Clinical trial roles</a>: ${esc(SC.reviews_awaiting)} links await human review (${esc(SC.reviews_adjudicated)} adjudicated).</li>` : ""}
          ${arr(SC.pending_candidates).map(c => `<li title="${esc(c.id)}">Unapproved alternative result set: ${esc(c.label)} — ${c.independently_verified ? "independently verified" : "verification incomplete"}, not used in the score.</li>`).join("")}</ul></section>
    </div>
    <section class="panel"><h2>Evidence agents</h2><p class="small muted">"Run completed" means the agent finished; "output checks passed" means its output met its data contract. Neither is a scientific validation.</p><div class="agents">${L.agents.map(agentCard).join("")}</div></section>
    <section class="panel"><h2>Pipeline dependencies</h2>${chartDag(L.stages, {title: "Pipeline stages in dependency order", caption: "Arrows point from a stage to the stages that use its output. Each box shows the stage identifier and its tracked state."})}
      ${chartBars(Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({label: human(k), value: v, text: String(v), cls: "st-" + k})), {title: "Stages by tracked state", max: L.stages.length, left: 290, xLabel: "number of stages"})}</section>
    <section class="panel"><h2>Recent runs</h2>${chartTimeline(L.history, {title: "Recent tracked runs", caption: "Each bar spans a run's start and finish; very short runs are drawn with a minimum width."})}</section>`;
  return {html, after: bindLiveActions};
}
async function viewAgent(id) {
  const d = await api("/api/agent?id=" + encodeURIComponent(id || ""));
  if (d.__error || d.error) return errBox(d.__error || d.error);
  const sess = await liveSessionGet(), L = lastStatus || {};
  const busy = arr(L.stages).some(x => x.status === "RUNNING") || liveLaunchActive || !!L.manifest_error;
  const pol = (sess || {}).policy || {};
  const art = (rows, kind) => `<table class="arts"><thead><tr><th scope="col">${kind}</th><th scope="col">state</th><th scope="col">modified</th></tr></thead><tbody>${rows.map(r => `<tr><td><code>${esc(r.path)}</code></td><td class="small">${!r.exists ? '<span class="muted">absent</span>' : r.matches_last_success === false ? '<span class="warn">changed since last success</span>' : r.matches_last_success ? '<span class="ok">as used by last success</span>' : '<span class="muted">not fingerprinted</span>'}</td><td class="small">${esc(r.modified_utc ? ago(r.modified_utc) : "")}</td></tr>`).join("")}</tbody></table>`;
  const env = d.envelope;
  const fb = liveFeedback ? `<div class="banner b-${esc(liveFeedback.level === "ok" ? "info" : liveFeedback.level)}" role="status">${esc(liveFeedback.text)}</div>` : "";
  const html = `<div class="crumbs small"><a href="#run">Run Center</a> › ${esc(d.name)}</div>
    <section class="panel"><h2>${esc(d.name)} <span class="kind k-${esc(d.kind.replace(/\s+/g, "-"))}" title="${esc(d.kind)}">${esc(d.kind === "VPS input" ? "checks a score input; does not change the score" : d.kind === "annotation" ? "annotation only" : "diagnostic, not in the score")}</span> <span class="small muted">agent ${esc(d.id)}</span></h2>
      <p>${esc(d.scope || "")}</p><div class="small muted">Role in the score: ${esc(d.role || "")}</div><div class="small muted">Sources: ${esc(d.sources || "")}</div>
      <div class="small">Implementation <code>${esc(d.module || "")}</code>${d.tests ? ` · tests <code>${esc(d.tests)}</code>` : ""} · output <code>${esc(d.output)}</code></div></section>
    ${fb}
    <section class="panel"><h2>Output validation</h2>${env.present ? `<div>${badge(env.run_status || "UNKNOWN")} envelope ${env.valid ? '<span class="ok">valid</span>' : '<span class="bad">invalid</span>'} · generated ${esc(ago(env.generated_utc))} · version <code>${esc(env.agent_version || "")}</code>${arr(env.stale_inputs).length ? ` · <span class="warn">inputs changed: ${env.stale_inputs.map(esc).join(", ")}</span>` : ' · <span class="ok">inputs unchanged</span>'}</div>
      <div class="small cov">${esc(env.coverage_line || "")}</div>
      ${arr(env.diagnostics).length ? `<ul class="small">${env.diagnostics.map(x => `<li>${esc(x.level)} ${esc(x.code)}: ${esc(x.message)}</li>`).join("")}</ul>` : '<div class="small muted">No diagnostics.</div>'}
      ${arr(env.limitations).length ? `<details class="small"><summary>Limitations (${env.limitations.length})</summary><ul>${env.limitations.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}` : '<div class="bad">Output unavailable.</div>'}</section>
    ${d.stages.map(x => `<section class="panel"><h2>Stage ${esc(x.id)} ${badge(x.status || "UNKNOWN")} <span class="small muted">${esc(x.name)}</span></h2>
      <div class="small">${esc(x.purpose || "")}</div>
      <div class="small">Depends on: ${arr(x.depends_on).map(u => `<code>${esc(u)}</code>`).join(" ") || "—"} · dashboard policy <strong>${esc(x.policy.class)}</strong> <span class="muted">${esc(x.policy.reason)}</span></div>
      ${arr(x.reasons).length ? `<div class="small warn">${x.reasons.map(esc).join("; ")}</div>` : ""}${arr(x.warnings).length ? `<div class="small warn">${x.warnings.map(esc).join("; ")}</div>` : ""}
      <div class="small">${x.status === "RUNNING" ? `<span class="pulse" aria-hidden="true"></span> running ${esc(dur(x.elapsed_s))}${x.last_activity && x.last_activity.line ? ` · <code>${esc(x.last_activity.line)}</code>` : ""}` : x.last_attempt ? `Last attempt ${badge(x.last_attempt.status)} <code>${esc(x.last_attempt.run_id)}</code>${x.last_attempt.duration_s != null ? " · " + esc(dur(x.last_attempt.duration_s)) : ""} · ${esc(ago(x.last_attempt.finished_utc || x.last_attempt.started_utc))}${x.last_attempt.exit_code != null ? " · exit " + esc(x.last_attempt.exit_code) : ""}` : "No tracked attempt."}${x.code_fingerprint_recorded === false ? ' · <span class="muted">no code fingerprint</span>' : ""}</div>
      <div class="stage-act">${liveActionButton(x.id, (pol[x.id] || {}).class, busy, "Run " + x.id)}</div>
      <div class="grid2">${art(x.inputs, "input")}${art(x.outputs, "output")}</div>
      ${x.log_tail ? `<details${x.status === "RUNNING" || (x.last_attempt && x.last_attempt.status === "FAILED") ? " open" : ""}><summary class="small">Log of ${esc((x.last_attempt || {}).run_id || "")}</summary><pre class="small">${esc(x.log_tail)}</pre></details>` : ""}</section>`).join("")}`;
  return {html, after: bindLiveActions};
}

// ---------- Live Pipeline: real launches through scripts/run_stage.py (POST /api/run) ----------
// The server decides what may run (policy + nonce + same-origin) and the runner's lock decides conflicts; this view
// only asks and then shows what the run manifest and the launch records say. Opening it starts nothing.
let liveSession = null, liveConfirm = null, liveFeedback = null, liveBusyPost = false, liveLaunchActive = false;
async function liveSessionGet(force) {
  if (!liveSession || force) { const s = await api("/api/session"); liveSession = s.__error ? null : s; }
  return liveSession;
}
async function livePost(body) {
  if (liveBusyPost) return;
  liveBusyPost = true;
  try {
    let r, data = {};
    // A restarted server issues a new nonce; the page then holds a stale one. Renew it once and retry, so the
    // user's click is not lost (a cross-site page still cannot read a nonce).
    for (let attempt = 0; attempt < 2; attempt++) {
      const sess = await liveSessionGet(attempt > 0);
      if (!sess) { liveFeedback = {level: "bad", text: "Could not obtain a session from the server."}; return; }
      const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), API_TIMEOUT_MS);
      try {
        r = await fetch("/api/run", {method: "POST", cache: "no-store", credentials: "same-origin", signal: ctl.signal,
          headers: {"Content-Type": "application/json", "X-EviRep-Nonce": sess.session_nonce}, body: JSON.stringify(body)});
        try { data = await r.json(); } catch (e) { data = {}; }
      } catch (e) {
        liveFeedback = {level: "bad", text: "Launch request failed: " + (e.name === "AbortError" ? "timed out" : "server unreachable") + ". Nothing was confirmed as started."};
        return;
      } finally { clearTimeout(t); }
      if (!(r.status === 403 && /nonce/.test(data.error || ""))) break;
    }
    if (r.status === 202) liveLaunchActive = true;
    if (r.status === 202) liveFeedback = {level: "ok", text: `Launch ${data.launch_id} accepted: ${data.command}. Its tracked run appears below once the runner claims it.`};
    else if (r.status === 403 && /nonce/.test(data.error || "")) { liveSession = null; liveFeedback = {level: "bad", text: (data.error || "refused") + " (even after renewing the session)."}; }
    else liveFeedback = {level: r.status === 409 || r.status === 428 ? "warn" : "bad", text: `HTTP ${r.status}: ${data.error || "refused"}`};
    liveConfirm = null;
  } finally {
    liveBusyPost = false;
    clearTimeout(pollTimer); poll();              // show the new state now, not at the next tick
  }
}
// Plain-language launch policy: what the safeguard is, why, and the safe alternative (codes kept in the tooltip).
function policyText(p) {
  if (!p || !p.class) return '<span class="muted">Policy unavailable (session not loaded)</span>';
  if (p.class === "ALLOWED") return `<span class="ok" title="ALLOWED">Can run here</span><div class="muted">Works offline; does not change approved data.</div>`;
  if (p.class === "CONFIRM") return `<span class="warn" title="CONFIRM">Runs after confirmation</span><div class="muted">It ${esc(p.reason)}.</div>`;
  const prot = /protected\/approved artefacts \(([^)]*)\)/.exec(p.reason || "");
  if (prot) return `<span title="REFUSED">Needs owner approval</span><div class="muted">It would rewrite approved research data. Safe workflow: the owner reviews it and runs it from the command line in an isolated copy first.</div><details><summary>Files it would rewrite</summary>${prot[1].split(", ").map(f => `<code>${esc(f)}</code>`).join(" ")}</details>`;
  if (/run from the command line/.test(p.reason || "")) return `<span title="REFUSED">Command line only</span><div class="muted">It needs live external services without a cache: ${esc(p.reason.split(";")[0])}.</div>`;
  return `<span title="REFUSED">Not available from this screen</span><div class="muted">${esc(p.reason)}.</div>`;
}
async function viewLive() {
  const [sess, st, la, LV] = await Promise.all([liveSessionGet(), api("/api/status"), api("/api/launches"), api("/api/live")]);
  if (st.__error) return errBox(st.__error);
  const depthOf = Object.fromEntries(arr((LV || {}).stages).map(x => [x.id, x.depth]));
  const pol = (sess || {}).policy || {}, runningStages = arr(st.stages).filter(x => x.status === "RUNNING");
  const launchRunning = arr((la || {}).launches).some(l => l.state === "RUNNING");
  liveLaunchActive = launchRunning;              // poll fast from the moment a launch exists, not only once RUNNING is seen
  const busy = runningStages.length > 0 || launchRunning || st.manifest_error;
  const cls = c => c === "ALLOWED" ? "ok" : c === "CONFIRM" ? "warn" : "muted";
  const action = x => {
    const p = pol[x.id] || {class: "REFUSED", reason: "no policy (session unavailable)"};
    if (p.class === "REFUSED") return `<span class="small muted">not from this screen</span>`;
    if (busy) return `<button type="button" disabled>Run</button>`;
    if (p.class === "CONFIRM" && liveConfirm === x.id)
      return `<div class="small warn">${esc(p.reason)}.</div><button type="button" data-run="${esc(x.id)}" data-confirm="1">Confirm run</button> <button type="button" data-cancel-confirm="1">Back</button>`;
    return `<button type="button" data-run="${esc(x.id)}"${p.class === "CONFIRM" ? ' data-ask="1"' : ""}>${p.class === "CONFIRM" ? "Run…" : "Run"}</button>`;
  };
  const fb = liveFeedback ? `<div class="banner b-${esc(liveFeedback.level === "ok" ? "info" : liveFeedback.level)}" role="status">${esc(liveFeedback.text)}</div>` : "";
  const nAllowed = Object.values(pol).filter(p => p.class === "ALLOWED").length;
  const html = `<section class="panel"><h2>Pipeline stages</h2>
    <p class="small">Start a stage or the whole permitted pipeline. Only one run happens at a time; a failed run restores the previous outputs; stages that would rewrite approved research data cannot be started here. While a stage runs you see its elapsed time and latest log line (stages do not report a percentage). Stopping a run is not offered because it would skip the restore step.</p>
    <details class="small"><summary>Technical details</summary>Runs are executed by <code>scripts/run_stage.py</code>, which records every run in <code>data/run_manifest.json</code>, refuses conflicting runs, applies per-stage time limits and publishes the score only after independent verification. ${esc((sess || {}).cancellation || "")}</details>
    ${st.manifest_error ? `<div class="banner b-bad">Run records unreadable (${esc(st.manifest_error)}): launches are disabled. Diagnose with <code>./venv/bin/python scripts/run_stage.py --check-manifest</code>.</div>` : ""}
    ${fb}
    <div><button type="button" data-pipeline="1"${busy ? " disabled" : ""}>Run all ${esc(nAllowed)} permitted stages</button> <span class="small muted">in dependency order; stages with unchanged inputs are skipped</span>
      ${busy ? `<span class="small warn"> A run is in progress${runningStages.length ? ": " + runningStages.map(x => esc(x.id)).join(", ") : ""}; new launches wait.</span>` : ""}</div>
    ${chartDag(st.stages.map(x => ({...x, depth: (depthOf[x.id] ?? 0), upstream: arr(x.upstream).map(u => u.id), latest_attempt_failed: x.latest_attempt_failed})), {title: "Pipeline stages in dependency order", caption: "Arrows point from a stage to the stages that use its output."})}
    <div class="tablewrap"><table><thead><tr><th scope="col">stage</th><th scope="col">state</th><th scope="col">activity</th><th scope="col">last successful run</th><th scope="col">depends on</th><th scope="col">can it run here?</th><th scope="col">action</th></tr></thead><tbody>
    ${arr(st.stages).map(x => { const p = pol[x.id] || {}; return `<tr><td><strong class="nowrap">${esc(x.id)}</strong> <span class="small muted">${esc(x.name)}</span></td>
      <td>${badge(x.status)}${arr(x.reasons).length ? `<div class="small warn">${x.reasons.map(esc).join("; ")}</div>` : ""}${arr(x.warnings).length ? `<div class="small warn">${x.warnings.map(w => esc(w)).join("; ")}</div>` : ""}</td>
      <td class="small">${x.status === "RUNNING" ? `running ${esc(dur(x.elapsed_s))}${x.last_activity && x.last_activity.line ? `<div><code>${esc(x.last_activity.line)}</code></div><div class="muted">log written ${esc(dur(x.last_activity.log_age_s))} ago</div>` : '<div class="muted">no log output yet</div>'}` : x.last_attempt ? `${badge(x.last_attempt.status)}${x.last_attempt.duration_s != null ? " · " + esc(dur(x.last_attempt.duration_s)) : ""}${logLink(x.last_attempt)}` : '<span class="muted">—</span>'}</td>
      <td class="small">${x.last_success ? `<code>${esc(x.last_success.run_id)}</code><div class="muted">${esc(x.last_success.finished_utc || "")}</div>` : '<span class="muted">none</span>'}</td>
      <td class="small">${arr(x.upstream).map(u => `${esc(u.id)} ${badge(u.status || "?")}`).join(" ") || '<span class="muted">—</span>'}</td>
      <td class="small">${policyText(p)}</td>
      <td class="small">${action(x)}</td></tr>`; }).join("")}</tbody></table></div></section>
    <section class="panel"><h2>Run history</h2>${chartTimeline(arr((LV || {}).history), {title: "Recent tracked runs", n: 15, caption: "Each bar spans a run's start and finish."})}</section>
    <section class="panel"><h2>Launches from this screen</h2>
    <p class="small muted">What this dashboard asked the runner to do (<code>data/_runs/_ui_launches/</code>). The run table above, from the run manifest, is the authority on outcomes.</p>
    ${(la || {}).__error ? errBox(la.__error) : arr(la.launches).length ? arr(la.launches).map(l => `<details${l.state === "RUNNING" ? " open" : ""}><summary><code>${esc(l.launch_id)}</code> ${badge(l.state)} ${esc(l.command || "")}${l.exit_code != null ? ` · exit ${esc(l.exit_code)}` : ""}${l.confirmed ? " · confirmed" : ""}</summary><pre class="small">${esc(arr(l.log_tail).join("\n") || "(no output yet)")}</pre></details>`).join("") : '<div class="empty">No launches from the dashboard yet.</div>'}</section>`;
  const after = () => {
    $main.querySelectorAll("button[data-run]").forEach(b => b.addEventListener("click", () => {
      if (b.dataset.ask) { liveConfirm = b.dataset.run; route({keepScroll: true}); return; }
      livePost(b.dataset.confirm ? {stage: b.dataset.run, confirm: true} : {stage: b.dataset.run});
    }));
    $main.querySelectorAll("button[data-cancel-confirm]").forEach(b => b.addEventListener("click", () => { liveConfirm = null; route({keepScroll: true}); }));
    $main.querySelectorAll("button[data-pipeline]").forEach(b => b.addEventListener("click", () => livePost({pipeline: true})));
  };
  return {html, after};
}

// ---------- router ----------
const VIEWS = {overview: viewOverview, drugs: viewDrugs, evidence: viewEvidence, mechanism: viewMechanism,
  conflicts: viewConflicts, review: viewReview, compare: viewCompare, validation: viewValidation, technical: viewTechnical,
  pipeline: viewPipeline, agents: viewAgents, cases: viewCases, live: viewLive, run: viewDashboard, dashboard: viewDashboard, agent: viewAgent};
// Five primary sections; every older address still opens its page inside the section it now belongs to.
const SECTIONS = {
  overview: {label: "Overview", tabs: [["overview", "Overview"]]},
  drugs: {label: "Candidates", tabs: [["drugs", "Candidate table"], ["compare", "Compare"]]},
  evidence: {label: "Evidence", tabs: [["evidence", "All evidence"], ["mechanism", "Mechanism"], ["conflicts", "Conflicting evidence"], ["review", "Trial-role review"]]},
  validation: {label: "Validation", tabs: [["validation", "Validation"]]},
  run: {label: "Run Center", tabs: [["run", "Pipeline health"], ["live", "Stages and runs"], ["technical", "Advanced diagnostics"]]},
};
const SECTION_OF = {overview: "overview", drugs: "drugs", compare: "drugs", evidence: "evidence", mechanism: "evidence", conflicts: "evidence",
  review: "evidence", validation: "validation", run: "run", dashboard: "run", live: "run", agent: "run", technical: "run",
  pipeline: "run", agents: "run", cases: "run"};
const TAB_OF = {dashboard: "run", agent: "run", pipeline: "technical", agents: "technical", cases: "technical"};
function subnav(view) {
  const sec = SECTIONS[SECTION_OF[view]], cur = TAB_OF[view] || view;
  if (!sec || sec.tabs.length < 2) return "";
  return `<nav class="subnav" aria-label="${esc(sec.label)} pages">${sec.tabs.map(([v, l]) => `<a href="#${v}"${v === cur ? ' aria-current="page"' : ""}>${esc(l)}</a>`).join("")}</nav>`;
}
const LIVE_VIEWS = new Set(["dashboard", "run", "agent", "live"]);    // re-rendered on every status poll
let routeSeq = 0, firstRoute = true, lastRenderedHtml = null;
function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  const cut = raw.indexOf("/");
  const view = cut < 0 ? raw : raw.slice(0, cut), rest = cut < 0 ? "" : raw.slice(cut + 1);
  let arg;
  try { arg = rest ? decodeURIComponent(rest) : undefined; } catch (e) { arg = undefined; }   // malformed %-escape
  return {view: VIEWS[view] ? view : "overview", arg};     // the researcher overview is the entry point
}
async function route(opts) {
  opts = opts || {};
  const seq = ++routeSeq, {view, arg} = parseHash(), y = window.scrollY;
  const navView = SECTION_OF[view] || view;
  document.querySelectorAll("#nav button").forEach(b => b.dataset.view === navView ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  $main.setAttribute("aria-busy", "true");
  if (!opts.keepScroll) $main.innerHTML = '<div class="empty">Loading…</div>';
  let out;
  try { out = await VIEWS[view](arg); } catch (e) { out = errBox("this view failed to render (" + (e && e.name || "Error") + ")"); }
  if (seq !== routeSeq) return;                 // a newer navigation superseded this one
  const res = typeof out === "string" ? {html: out} : out;
  res.html = subnav(view) + res.html;
  // A background refresh that produced identical markup leaves the DOM alone: replacing unchanged buttons
  // between a user's mouse-down and mouse-up would swallow the click (Live pipeline refreshes every poll).
  if (opts.keepScroll && res.html === lastRenderedHtml) { $main.setAttribute("aria-busy", "false"); return; }
  lastRenderedHtml = res.html;
  $main.innerHTML = res.html;
  if (res.after) res.after();
  $main.querySelectorAll(".chart .bar[data-key]").forEach(g => {          // ranking bars open the candidate (mouse and keyboard)
    const go = () => { location.hash = drugHref(g.dataset.key).replace(/^#/, ""); };
    g.addEventListener("click", go);
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  $main.setAttribute("aria-busy", "false");
  const target = $main.querySelector("[data-scroll]");          // e.g. a candidate chosen from the ranking
  if (opts.keepScroll) window.scrollTo(0, y);
  else if (target) target.scrollIntoView({block: "start"}); else window.scrollTo(0, 0);
  if (!firstRoute && !opts.keepScroll) $main.focus({preventScroll: true});
  $main.dataset.version = liveVersion || "";
  firstRoute = false;
  const sec = SECTIONS[navView], tab = sec && sec.tabs.find(([v]) => v === (TAB_OF[view] || view));
  document.title = "EviRep · " + (sec ? sec.label + (tab && sec.tabs.length > 1 ? " · " + tab[1] : "") : "Research application");
}
document.getElementById("nav").addEventListener("click", e => {
  const b = e.target.closest("button"); if (b) location.hash = b.dataset.view;
});
// The skip link must not change the hash (the hash is the router's state).
document.getElementById("skip").addEventListener("click", e => { e.preventDefault(); $main.focus(); });
window.addEventListener("hashchange", () => route());
(async () => {                 // status first, so the first render already knows its data version
  const st = await api("/api/status");
  if (!st.__error) { liveVersion = st.data_version; renderLive(st); }
  await route();
  pollTimer = setTimeout(poll, POLL_MS);
})();
