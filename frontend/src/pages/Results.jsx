import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Page, PageTitle, Card, BtnPrimary, BtnGhost } from '../components/UI'
import { listUitvragen, getUitvraag, downloadUitvraag } from '../services/api'

const STATUS_STYLE = {
  VOLTOOID:     { bg: 'var(--green-light)', fg: 'var(--green)', label: 'Voltooid' },
  GEDEELTELIJK: { bg: 'var(--amber-light)', fg: 'var(--amber)', label: 'Gedeeltelijk' },
  MISLUKT:      { bg: 'var(--red-light)', fg: 'var(--red)', label: 'Mislukt' },
}
const ANTW_STYLE = {
  OK:        { fg: 'var(--green)' },
  GEEN_DATA: { fg: 'var(--amber)' },
  FOUT:      { fg: 'var(--red)' },
}

function Badge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.VOLTOOID
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, background: s.bg, color: s.fg }}>{s.label}</span>
}

export default function Results() {
  const [params, setParams] = useSearchParams()
  const [lijst, setLijst] = useState([])
  const [actief, setActief] = useState(null)
  const [fout, setFout] = useState(null)
  const gekozenId = params.get('uitvraag')

  useEffect(() => { listUitvragen().then(setLijst).catch(e => setFout(e.message)) }, [])
  useEffect(() => {
    if (gekozenId) getUitvraag(gekozenId).then(setActief).catch(e => setFout(e.message))
    else setActief(null)
  }, [gekozenId])

  function fmtWaarde(a) {
    if (a.status !== 'OK' || a.waarde == null) return '—'
    return `${a.waarde}${a.eenheid ? ' ' + a.eenheid : ''}`
  }

  return (
    <Page>
      <PageTitle badge="Resultaten" title="📊 Resultaten"
        sub="Bekijk de antwoorden op je uitvragen, vergelijk tussen zorgaanbieders en download de resultaten als CSV of Excel. Ophalen kan ook via de API." />
      {fout && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}>
        <span style={{ color: 'var(--red)', fontSize: 14 }}>{fout}</span></Card>}

      {!actief && (
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead><tr style={{ background: 'var(--bg)', textAlign: 'left' }}>
              {['Uitwisselprofiel', 'Antwoorden', 'Status', 'Datum', ''].map(h =>
                <th key={h} style={{ padding: '12px 16px', fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {lijst.map(u => (
                <tr key={u.id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text)' }}>{u.profiel_label}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text2)' }}>{u.aantal_antwoorden}</td>
                  <td style={{ padding: '12px 16px' }}><Badge status={u.status} /></td>
                  <td style={{ padding: '12px 16px', color: 'var(--text3)', fontSize: 13 }}>{u.created_at ? new Date(u.created_at).toLocaleString('nl-NL') : '—'}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <BtnGhost onClick={() => setParams({ uitvraag: u.id })}>Bekijken →</BtnGhost></td>
                </tr>
              ))}
              {lijst.length === 0 && <tr><td colSpan={5} style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>Nog geen uitvragen. Start er een via Opvragen.</td></tr>}
            </tbody>
          </table>
        </Card>
      )}

      {actief && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <BtnGhost onClick={() => setParams({})}>← Overzicht</BtnGhost>
              <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{actief.profiel_label}</span>
              <Badge status={actief.status} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <BtnGhost onClick={() => downloadUitvraag(actief.id, 'csv')}>⬇ CSV</BtnGhost>
              <BtnPrimary onClick={() => downloadUitvraag(actief.id, 'xlsx')}>⬇ Excel</BtnPrimary>
            </div>
          </div>

          <Card style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead><tr style={{ background: 'var(--bg)', textAlign: 'left' }}>
                {['Zorgaanbieder', 'Indicator', 'Waarde', 'Status'].map(h =>
                  <th key={h} style={{ padding: '12px 16px', fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>{h}</th>)}
              </tr></thead>
              <tbody>
                {actief.antwoorden.map(a => {
                  const s = ANTW_STYLE[a.status] || ANTW_STYLE.OK
                  return (
                    <tr key={a.id} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text)' }}>{a.zorgaanbieder}</td>
                      <td style={{ padding: '12px 16px', color: 'var(--text2)' }}>{a.indicator}</td>
                      <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text)' }}>{fmtWaarde(a)}</td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: s.fg }}>{a.status}</span>
                        {a.toelichting && <div style={{ fontSize: 11, color: 'var(--text3)' }}>{a.toelichting}</div>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>

          <Card style={{ background: 'var(--blue-light)', border: '1px solid var(--blue-mid)' }}>
            <div style={{ fontSize: 13, color: 'var(--blue-dark)' }}>
              <b>Via de API ophalen:</b> <code style={{ background: '#fff', padding: '2px 6px', borderRadius: 4 }}>GET /api/uitvragen/{actief.id}</code> (met Bearer-token).
            </div>
          </Card>
        </>
      )}
    </Page>
  )
}
