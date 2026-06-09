import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Page, PageTitle, Card, StatusDot } from '../components/UI'
import { getMeta, getHealth } from '../services/api'

const MODULES = [
  { to: '/opvragen', icon: '🔎', title: 'Opvragen (query-flow)',
    desc: 'Dataset kiezen → zorgaanbieders → uitwisselprofiel → SPARQL-query → resultaten.', status: 'Gepland' },
  { to: '/beheer', icon: '🏢', title: 'Beheer / Registratie',
    desc: 'Organisaties, endpoints en DID-registratie beheren (beheermodule).', status: 'Gepland' },
  { to: '/resultaten', icon: '📊', title: 'Resultaten',
    desc: 'Opgevraagde indicatorresultaten bekijken, vergelijken en exporteren.', status: 'Gepland' },
]

export default function Home() {
  const navigate = useNavigate()
  const [meta, setMeta] = useState(null)
  const [backendOk, setBackendOk] = useState(null)

  useEffect(() => {
    getHealth().then(() => setBackendOk(true)).catch(() => setBackendOk(false))
    getMeta().then(setMeta).catch(() => {})
  }, [])

  return (
    <Page>
      <PageTitle
        badge="KIK-Starter · Rhadix editie"
        title="Welkom bij de KIK-Starter"
        sub="Een herbouw van de ZIN KIK-V Starter in de Rhadix-stack. Dit is de applicatie-shell — de functionele modules worden stap voor stap toegevoegd."
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20, marginBottom: 28 }}>
        {MODULES.map(m => (
          <Card key={m.to} onClick={() => navigate(m.to)}
            style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 150 }}>
            <div style={{ fontSize: 28 }}>{m.icon}</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{m.title}</div>
            <div style={{ fontSize: 13, color: 'var(--text3)', lineHeight: 1.5, flex: 1 }}>{m.desc}</div>
            <span style={{ alignSelf: 'flex-start', fontSize: 11, fontWeight: 700, color: 'var(--amber)', background: 'var(--amber-light)', padding: '3px 10px', borderRadius: 99 }}>{m.status}</span>
          </Card>
        ))}
      </div>

      <Card style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
        <StatusDot ok={backendOk} label={backendOk == null ? 'Backend controleren…' : backendOk ? 'Backend verbonden' : 'Backend onbereikbaar'} />
        {meta && <span style={{ fontSize: 12, color: 'var(--text3)' }}>Versie {meta.version} · omgeving: {meta.environment}</span>}
      </Card>
    </Page>
  )
}
