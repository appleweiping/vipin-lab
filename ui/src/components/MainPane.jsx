import { useState, useRef, useEffect } from "react"
import { api } from "../api.js"
import SessionView from "./SessionView.jsx"
import "./MainPane.css"

const MODES = [
  { id: "discover",  icon: "🔬", label: "Discover",  placeholder: "Domain to scan (e.g. LLM4Rec, uncertainty quantification...)", color: "#5b8af5" },
  { id: "extend",    icon: "🔗", label: "Extend",    placeholder: "Domain of your existing project...", color: "#4ade80" },
  { id: "transfer",  icon: "⚡", label: "Transfer",  placeholder: "Source domain (e.g. conformal prediction)...", color: "#fbbf24" },
]

export default function MainPane({ session, onResult }) {
  const [mode, setMode] = useState("discover")
  const [input, setInput] = useState("")
  const [input2, setInput2] = useState("")  // method (extend) or target (transfer)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState([])
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const taRef = useRef(null)
  const timerRef = useRef(null)

  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = "auto"
    ta.style.height = Math.min(ta.scrollHeight, 180) + "px"
  }, [input])

  useEffect(() => {
    if (loading) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
    } else {
      clearInterval(timerRef.current)
    }
    return () => clearInterval(timerRef.current)
  }, [loading])

  const handleSubmit = async () => {
    const q = input.trim()
    if (!q || loading) return
    setError(null)
    setLoading(true)
    setProgress([])

    try {
      let stream
      if (mode === "discover") {
        stream = api.discover(q)
      } else if (mode === "extend") {
        stream = api.extend(q, input2.trim() || q)
      } else {
        stream = api.transfer(q, input2.trim())
      }

      for await (const { event, data } of stream) {
        if (event === "progress") {
          setProgress(p => [...p.slice(-8), `${data.phase}: ${data.step}`])
        } else if (event === "done") {
          onResult(data)
          setInput("")
          setInput2("")
        } else if (event === "error") {
          setError(data.message)
        }
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      setProgress([])
    }
  }

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  const currentMode = MODES.find(m => m.id === mode)

  return (
    <div className="main-pane-inner">
      {/* Header */}
      <div className="pane-header">
        <div className="pane-title">
          <span className="pane-icon">⚗</span>
          <span>Vipin Lab</span>
          <span className="pane-sub">Autonomous Research System</span>
        </div>
        {session && <div className="session-id-badge"><span>session</span><code>{session.id?.slice(0,8)}</code></div>}
      </div>

      {/* Body */}
      <div className="pane-body">
        {!session && !loading && (
          <div className="empty-state">
            <div className="empty-icon">⚗</div>
            <div className="empty-title">Vipin Lab</div>
            <div className="empty-sub">Phenomenon-driven research discovery. Kill-first ideation. Evidence-gated pipeline.</div>
            <div className="mode-chips">
              {MODES.map(m => (
                <button key={m.id}
                  className={`mode-chip ${mode === m.id ? "mode-chip--active" : ""}`}
                  style={mode === m.id ? { borderColor: m.color, color: m.color, background: m.color + "18" } : {}}
                  onClick={() => setMode(m.id)}>
                  {m.icon} {m.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <div className="loading-state">
            <div className="loading-ring" style={{ borderTopColor: currentMode.color }} />
            <div className="loading-label">
              <span>{currentMode.icon} {currentMode.label}</span>
              <span className="loading-elapsed">{elapsed}s</span>
            </div>
            <div className="loading-sub">Running discovery pipeline…</div>
            {progress.length > 0 && (
              <div className="progress-log">
                {progress.map((p, i) => (
                  <div key={i} className="progress-line">
                    <span className="progress-dot">·</span> {p}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {session && !loading && <SessionView session={session} />}
      </div>

      {/* Error */}
      {error && (
        <div className="error-bar">
          <span>⚠ {error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Input */}
      <div className="input-area">
        <div className="mode-selector">
          {MODES.map(m => (
            <button key={m.id}
              className={`mode-btn ${mode === m.id ? "mode-btn--active" : ""}`}
              style={mode === m.id ? { borderColor: m.color, color: m.color } : {}}
              onClick={() => setMode(m.id)} disabled={loading} title={m.label}>
              <span>{m.icon}</span>
              <span className="mode-btn-label">{m.label}</span>
            </button>
          ))}
        </div>

        {mode === "extend" && (
          <input className="input-secondary" placeholder="Current method description..."
            value={input2} onChange={e => setInput2(e.target.value)} disabled={loading} />
        )}
        {mode === "transfer" && (
          <input className="input-secondary" placeholder="Target domain..."
            value={input2} onChange={e => setInput2(e.target.value)} disabled={loading} />
        )}

        <div className={`input-row ${loading ? "input-row--loading" : ""}`}
             style={{ "--focus-color": currentMode.color }}>
          <textarea ref={taRef} className="input-ta"
            placeholder={currentMode.placeholder}
            value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey} disabled={loading} rows={1} />
          <button className="send-btn"
            style={{ background: input.trim() && !loading ? currentMode.color : undefined }}
            onClick={handleSubmit} disabled={!input.trim() || loading}>
            {loading ? <span className="send-spin" style={{ borderTopColor: currentMode.color }} /> : "↑"}
          </button>
        </div>
      </div>
    </div>
  )
}
