import { useEffect, useRef, useState } from 'react'
import { Page, PageTitle, Card, BtnPrimary, BtnGhost, StatusPill } from '../components/UI'
import { getCapabilitiesOverzicht, importCapabilities } from '../services/api'

const VOORBEELD_CSV = `aanbieder_id_type,aanbieder_id,aanbieder_naam,software_leverancier,uitwisselprofiel,versie,status,laatst_bijgewerkt
kvk,30112233,Zorggroep De Linden,Nedap,igj-toezicht,1.0,productie,2026-02-01
kvk,44556677,Stichting Thuiszorg West,PinkRoccade,zorgkantoren-inkoop,1.0,productie,2026-01-20
`

function Stat({ label, value, kleur }) {
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 76 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>{label}</span>
      <span style={{ fontSize: 26, fontWeight: 800, color: kleur || 'var(--text)' }}>{value}</span>
    </Card>
  )
}

function AdminImport({ onDone }) {
  const fileRef = useRef(null)
  const [bezig, setBezig] = useState(false)
  const [res, setRes] = useState(null)
  const [fout, setFout] = useState(null)

  async function upload() {
    const f = fileRef.current?.files?.[0]
    if (!f) { setFout('Kies eerst een CSV-bestand.'); return }
    setBezig(true); setFout(null); setRes(null)
    try { const r = await importCapabilities(f); setRes(r); onDone?.() }
    catch (e) { setFout(e.message) } finally { setBezig(false) }
  }

  function downloadVoorbeeld() {
    const url = URL.createObjectURL(new Blob([VOORBEELD_CSV], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'uitwisselprofielen_voorbeeld.csv'
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }

  return (
    <Card style={{ marginBottom: 20, background: 'var(--bg2, #f8fafc)' }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 10 }}>
        Registry importeren (beheerder)
      </div>
      <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 12, lineHeight: 1.5 }}>
        Lees de door KIK-V Beheer aangeleverde CSV in (full refresh — de hele registry wordt vervangen).
        Kolommen: <code>aanbieder_id_type, aanbieder_id, aanbieder_naam, software_leverancier, uitwisselprofiel, versie, status, laatst_bijgewerkt</code>.
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <input ref={fileRef} type="file" accept=".csv,text/csv" style={{ fontSize: 13 }} />
        <BtnPrimary onClick={upload} disabled={bezig}>{bezig ? 'Importeren…' : 'Importeren'}</BtnPrimary>
        <BtnGhost onClick={downloadVoorbeeld}>Voorbeeld-CSV</BtnGhost>
      </div>
      {fout && <div style={{ color: 'var(--red)', fontSize: 13, marginTop: 10 }}>{fout}</div>}
      {res && (
        <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text2)' }}>
          ✓ Verwerkt: <b>{res.verwerkt}</b> · afgekeurd: <b style={{ color: res.afgekeurd ? 'var(--amber)' : 'inherit' }}>{res.afgekeurd}</b> (van {res.totaal})
          {res.redenen?.length > 0 && (
            <ul style={{ margin: '8px 0 0 18px', color: 'var(--text3)' }}>
              {res.redenen.slice(0, 8).map((r, i) => <li key={i}>regel {r.regel}: {r.redenen.join('; ')}</li>)}
            </ul>
          )}
        </div>
      )}
    </Card>
  )
}

export default function Dekking({ authUser }) {
  const [data, setData] = useState(null)
  const [fout, setFout] = useState(null)
  const [modus, setModus] = useState('profiel')   // 'profiel' | 'aanbieder'
  const [zoek, setZoek] = useState('')

  function laden() { getCapabilitiesOverzicht().then(setData).catch(e => setFout(e.message)) }
  useEffect(laden, [])

  const isAdmin = authUser?.role === 'PLATFORM_ADMIN'
  const q = zoek.trim().toLowerCase()

  return (
    <Page>
      <PageTitle badge="Dekking" title="🗂️ Uitwisselprofiel-dekking"
        sub="Welke zorgaanbieders hebben welke uitwisselprofielen (en versie) geïmplementeerd, en met welke status. Zo zie je vooraf aan wie je een uitvraag kunt richten." />

      {fout && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}><span style={{ color: 'var(--red)' }}>{fout}</span></Card>}

      {isAdmin && <AdminImport onDone={laden} />}

      {data && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14, marginBottom: 18 }}>
            <Stat label="Registraties" value={data.totaal} />
            <Stat label="Productie" value={data.status_telling.productie || 0} kleur="var(--green)" />
            <Stat label="Test / impl." value={(data.status_telling.test || 0) + (data.status_telling.implementatie || 0)} kleur="var(--amber)" />
            <Stat label="Uitgefaseerd" value={data.status_telling.uitgefaseerd || 0} kleur="var(--text3)" />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'inline-flex', background: 'var(--bg)', borderRadius: 'var(--radius)', padding: 3 }}>
              {[['profiel', 'Per profiel'], ['aanbieder', 'Per aanbieder']].map(([k, lbl]) => (
                <button key={k} onClick={() => setModus(k)} style={{
                  border: 'none', borderRadius: 'calc(var(--radius) - 2px)', padding: '7px 16px', fontSize: 13, fontWeight: 600,
                  cursor: 'pointer', fontFamily: 'var(--font)',
                  background: modus === k ? '#fff' : 'transparent', color: modus === k ? 'var(--text)' : 'var(--text3)',
                  boxShadow: modus === k ? 'var(--shadow)' : 'none',
                }}>{lbl}</button>
              ))}
            </div>
            <input value={zoek} onChange={e => setZoek(e.target.value)} placeholder="🔍 Zoek profiel of aanbieder…"
              style={{ padding: '9px 12px', borderRadius: 'var(--radius)', border: '1.5px solid var(--border)', fontSize: 14, fontFamily: 'var(--font)', minWidth: 240, outline: 'none' }} />
          </div>

          {modus === 'profiel' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {data.per_profiel.filter(p => !q || p.profiel_label.toLowerCase().includes(q) || p.aanbieders.some(a => a.aanbieder_naam.toLowerCase().includes(q))).map(p => (
                <Card key={p.profiel_key}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 10 }}>{p.profiel_label}
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text3)' }}> · {p.aanbieders.length} aanbieder(s)</span></div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {p.aanbieders.map((a, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '6px 0', borderTop: i ? '1px solid var(--border)' : 'none' }}>
                        <span style={{ fontSize: 14, color: 'var(--text2)' }}>{a.aanbieder_naam} <span style={{ color: 'var(--text3)', fontSize: 12 }}>· v{a.versie}</span></span>
                        <StatusPill status={a.status} />
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {modus === 'aanbieder' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {data.per_aanbieder.filter(a => !q || a.aanbieder_naam.toLowerCase().includes(q) || a.profielen.some(p => p.profiel_label.toLowerCase().includes(q))).map(a => (
                <Card key={a.aanbieder_naam}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginBottom: 2 }}>{a.aanbieder_naam}</div>
                  <div style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 10 }}>{[a.software_leverancier, a.geregistreerd ? 'geregistreerd' : 'niet geregistreerd'].filter(Boolean).join(' · ')}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {a.profielen.map((p, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '6px 0', borderTop: i ? '1px solid var(--border)' : 'none' }}>
                        <span style={{ fontSize: 14, color: 'var(--text2)' }}>{p.profiel_label} <span style={{ color: 'var(--text3)', fontSize: 12 }}>· v{p.versie}</span></span>
                        <StatusPill status={p.status} />
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </Page>
  )
}
