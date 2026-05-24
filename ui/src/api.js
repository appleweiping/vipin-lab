const BASE = '/api'

export async function* streamSSE(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop()
    for (const part of parts) {
      const lines = part.split('\n')
      let event = 'message', data = ''
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data = line.slice(5).trim()
      }
      if (data) yield { event, data: JSON.parse(data) }
    }
  }
}

export const api = {
  async get(path) {
    const r = await fetch(BASE + path)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  },
  discover: (domain, use_beam = true) =>
    streamSSE(`${BASE}/discover`, { domain, use_beam }),
  extend: (domain, method, results = '', limitations = '', n = 3) =>
    streamSSE(`${BASE}/extend`, { domain, method, results, limitations, n }),
  transfer: (source_domain, target_domain) =>
    streamSSE(`${BASE}/transfer`, { source_domain, target_domain }),
  pipeline: (id) => streamSSE(`${BASE}/pipeline/${id}`, {}),
  resume: (id) => streamSSE(`${BASE}/resume/${id}`, {}),
  ideas: (domain = '', status = '') =>
    api.get(`/ideas?domain=${encodeURIComponent(domain)}&status=${encodeURIComponent(status)}`),
  idea: (id) => api.get(`/ideas/${id}`),
  sessions: () => api.get('/sessions'),
  session: (id) => api.get(`/sessions/${id}`),
  health: () => api.get('/health'),
}
