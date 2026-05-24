import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import "./SessionView.css"

const ORIGIN_META = {
  phenomenon: { icon: "🔬", color: "#5b8af5", label: "Phenomenon" },
  extension:  { icon: "🔗", color: "#4ade80", label: "Extension" },
  transfer:   { icon: "⚡", color: "#fbbf24", label: "Transfer" },
  literature: { icon: "📚", color: "#a78bfa", label: "Literature" },
}

const STATUS_COLORS = {
  kill_tested: "#fbbf24", refined: "#4ade80", planned: "#22d3ee",
  running: "#22d3ee", ready: "#4ade80", killed: "#f87171", generated: "#636d94",
}

function ConfBar({ value }) {
  const pct = Math.round((value || 0) * 100)
  const color = pct >= 70 ? "#4ade80" : pct >= 40 ? "#fbbf24" : "#f87171"
  return (
    <div className="conf-bar">
      <div className="conf-track"><div className="conf-fill" style={{ width: `${pct}%`, background: color }} /></div>
      <span className="conf-label" style={{ color }}>{pct}%</span>
    </div>
  )
}

function IdeaCard({ idea, index }) {
  const [open, setOpen] = useState(false)
  const meta = ORIGIN_META[idea.origin] || ORIGIN_META.phenomenon
  const sc = STATUS_COLORS[idea.status] || "#636d94"

  return (
    <div className={`idea-card ${idea.status === "killed" ? "idea-card--killed" : ""}`}>
      <div className="idea-card-header" onClick={() => setOpen(o => !o)}>
        <span className="idea-num">#{index + 1}</span>
        <span className="idea-origin-icon">{meta.icon}</span>
        <div className="idea-title-wrap">
          <div className="idea-title">{idea.title}</div>
          <div className="idea-meta-row">
            <span className="idea-status" style={{ color: sc }}>{idea.status}</span>
            <span className="idea-score">N: <b>{idea.novelty_score?.toFixed(1)}</b></span>
            <span className="idea-score">F: <b>{idea.feasibility_score?.toFixed(1)}</b></span>
            <span className="idea-id">{idea.id?.slice(0, 8)}</span>
          </div>
        </div>
        <span className="idea-chevron">{open ? "▾" : "▸"}</span>
      </div>

      {open && (
        <div className="idea-card-body">
          {idea.phenomenon && (
            <div className="idea-field">
              <span className="field-label">Phenomenon</span>
              <div className="field-value">{idea.phenomenon}</div>
            </div>
          )}
          {idea.hypothesis && (
            <div className="idea-field">
              <span className="field-label">Hypothesis</span>
              <div className="field-value">{idea.hypothesis}</div>
            </div>
          )}
          {idea.proposed_method && (
            <div className="idea-field">
              <span className="field-label">Method</span>
              <div className="field-value md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{idea.proposed_method}</ReactMarkdown></div>
            </div>
          )}
          {idea.kill_argument && (
            <div className="idea-field idea-field--kill">
              <span className="field-label">Kill argument</span>
              <div className="field-value">{idea.kill_argument.slice(0, 300)}{idea.kill_argument.length > 300 ? "…" : ""}</div>
              {idea.kill_rebuttal && (
                <>
                  <span className="field-label" style={{ color: "#4ade80" }}>Rebuttal</span>
                  <div className="field-value">{idea.kill_rebuttal.slice(0, 300)}</div>
                </>
              )}
            </div>
          )}
          {idea.workspace_dir && (
            <div className="idea-actions">
              <code className="idea-cmd">vlab pipeline {idea.id?.slice(0, 8)}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PhenomenonCard({ p, index }) {
  const sev = Math.round(p.severity * 10)
  const bar = "█".repeat(sev) + "░".repeat(10 - sev)
  return (
    <div className="phenom-card">
      <div className="phenom-header">
        <span className="phenom-num">P{index + 1}</span>
        <span className="phenom-bar">{bar}</span>
        <span className="phenom-sev">{(p.severity * 100).toFixed(0)}%</span>
      </div>
      <div className="phenom-desc">{p.description}</div>
      {p.evidence?.length > 0 && (
        <div className="phenom-evidence">
          {p.evidence.slice(0, 2).map((e, i) => <span key={i} className="evidence-tag">{e}</span>)}
        </div>
      )}
    </div>
  )
}

function AnalogyCard({ a }) {
  const conf = Math.round(a.confidence * 100)
  return (
    <div className="analogy-card">
      <div className="analogy-header">
        <span className="analogy-icon">⚡</span>
        <span className="analogy-conf">{conf}% confidence</span>
        <span className="analogy-domains">{a.source_domain} → {a.target_domain}</span>
      </div>
      <div className="analogy-row"><span className="analogy-label">Source problem</span><span>{a.source_problem?.slice(0, 80)}</span></div>
      <div className="analogy-row"><span className="analogy-label">Target problem</span><span>{a.target_problem?.slice(0, 80)}</span></div>
      {a.structural_similarity && (
        <div className="analogy-row"><span className="analogy-label">Why it holds</span><span>{a.structural_similarity?.slice(0, 100)}</span></div>
      )}
    </div>
  )
}

export default function SessionView({ session }) {
  if (!session) return null
  const { phenomena = [], analogies = [], ideas = [] } = session
  const surviving = ideas.filter(i => i.status !== "killed")
  const killed = ideas.filter(i => i.status === "killed")

  return (
    <div className="session-view">
      {/* Stats row */}
      <div className="stats-row">
        <div className="stat-chip"><span className="stat-n">{phenomena.length}</span><span>phenomena</span></div>
        <div className="stat-chip"><span className="stat-n">{analogies.length}</span><span>analogies</span></div>
        <div className="stat-chip stat-chip--green"><span className="stat-n">{surviving.length}</span><span>survived</span></div>
        <div className="stat-chip stat-chip--red"><span className="stat-n">{killed.length}</span><span>killed</span></div>
      </div>

      {/* Phenomena */}
      {phenomena.length > 0 && (
        <section className="sv-section">
          <div className="sv-section-title">🔬 Phenomena Detected</div>
          <div className="phenom-list">
            {phenomena.map((p, i) => <PhenomenonCard key={p.id || i} p={p} index={i} />)}
          </div>
        </section>
      )}

      {/* Analogies */}
      {analogies.length > 0 && (
        <section className="sv-section">
          <div className="sv-section-title">⚡ Cross-Domain Analogies</div>
          <div className="analogy-list">
            {analogies.map((a, i) => <AnalogyCard key={i} a={a} />)}
          </div>
        </section>
      )}

      {/* Ideas */}
      {ideas.length > 0 && (
        <section className="sv-section">
          <div className="sv-section-title">
            💡 Ideas
            <span className="sv-section-sub">{surviving.length} survived kill-first · {killed.length} killed</span>
          </div>
          <div className="idea-list">
            {ideas.map((idea, i) => <IdeaCard key={idea.id || i} idea={idea} index={i} />)}
          </div>
        </section>
      )}
    </div>
  )
}
