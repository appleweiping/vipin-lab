import { useState, useEffect, useCallback } from "react"
import Sidebar from "./components/Sidebar.jsx"
import MainPane from "./components/MainPane.jsx"
import { api } from "./api.js"
import "./App.css"

export default function App() {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [serverOk, setServerOk] = useState(null)

  useEffect(() => {
    api.health().then(() => setServerOk(true)).catch(() => setServerOk(false))
  }, [])

  const refreshSessions = useCallback(async () => {
    try { setSessions(await api.sessions()) } catch {}
  }, [])

  useEffect(() => { refreshSessions() }, [refreshSessions])

  const openSession = useCallback(async (id) => {
    try { setActiveSession(await api.session(id)) } catch {}
  }, [])

  const onNewResult = useCallback((session) => {
    setActiveSession(session)
    refreshSessions()
  }, [refreshSessions])

  return (
    <div className="app-shell">
      {serverOk === false && (
        <div className="server-banner">
          ⚠ Backend not reachable — run <code>uvicorn api.server:app --reload --port 8001</code>
        </div>
      )}
      <Sidebar sessions={sessions} activeId={activeSession?.id}
               onSelect={openSession} onNew={() => setActiveSession(null)} />
      <main className="main-pane">
        <MainPane session={activeSession} onResult={onNewResult} />
      </main>
    </div>
  )
}
