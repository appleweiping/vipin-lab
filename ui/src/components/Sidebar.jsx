import { useState } from "react"
import "./Sidebar.css"

const MODE_META = {
  discover:  { icon: "🔬", color: "#5b8af5", label: "Discover" },
  extend:    { icon: "🔗", color: "#4ade80", label: "Extend" },
  transfer:  { icon: "⚡", color: "#fbbf24", label: "Transfer" },
}

function timeAgo(iso) {
  const d = Date.now() - new Date(iso).getTime()
  const m = Math.floor(d / 60000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function Sidebar({ sessions, activeId, onSelect, onNew }) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar-header">
        {!collapsed && (
          <div className="sidebar-brand">
            <span className="brand-icon">⚗</span>
            <span className="brand-name">Vipin Lab</span>
          </div>
        )}
        <button className="icon-btn" onClick={() => setCollapsed(c => !c)}
                title={collapsed ? "Expand" : "Collapse"}>
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      {!collapsed && (
        <>
          <button className="new-btn" onClick={onNew}>
            <span>＋</span> New Session
          </button>
          <div className="section-label">Recent</div>
          <nav className="session-list">
            {sessions.length === 0 && <div className="empty">No sessions yet</div>}
            {sessions.map(s => {
              const meta = MODE_META[s.mode] || MODE_META.discover
              const pct = s.ideas_count > 0 ? Math.round(s.surviving / s.ideas_count * 100) : 0
              return (
                <button key={s.id}
                  className={`session-item ${s.id === activeId ? "session-item--active" : ""}`}
                  onClick={() => onSelect(s.id)}>
                  <span className="mode-dot" style={{ background: meta.color }} />
                  <div className="session-info">
                    <div className="session-domain">{s.domain}</div>
                    <div className="session-meta">
                      <span style={{ color: meta.color }}>{meta.icon} {meta.label}</span>
                      <span className="session-stats">{s.surviving}/{s.ideas_count} ideas</span>
                      <span className="session-time">{timeAgo(s.created_at)}</span>
                    </div>
                  </div>
                </button>
              )
            })}
          </nav>
        </>
      )}
    </aside>
  )
}
