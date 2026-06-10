import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Page, PageTitle, Card, BtnPrimary, BtnGhost } from '../components/UI'
import { listProfielen, getProfiel, listZorgaanbieders, createUitvraag } from '../services/api'

const STAPPEN = ['Uitwisselprofiel', 'Indicatoren', 'Zorgaanbieders', 'Versturen']

function Stepper({ stap }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
      {STAPPEN.map((s, i) => {
        const done = i < stap, active = i === stap
        return (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontSize: 13, fontWeight: 700,
              background: active ? 'var(--blue)' : done ? 'var(--green)' : 'var(--bg)',
              color: active || done ? '#fff' : 'var(--text3)',
              border: active || done ? 'none' : '1px solid var(--border2)',
            }}>{done ? '✓' : i + 1}</span>
            <span style={{ fontSize: 13, fontWeight: active ? 700 : 500, color: active ? 'var(--text)' : 'var(--text3)' }}>{s}</span>
            {i < STAPPEN.length - 1 && <span style={{ color: 'var(--border2)', margin: '0 4px' }}>→</span>}
          </div>
        )
      })}
    </div>
  )
}

function SelectRow({ checked, onToggle, title, sub, right }) {
  return (
    <div onClick={onToggle} style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', cursor: 'pointer',
      borderRadius: 'var(--radius)', border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border)'}`,
      background: checked ? 'var(--blue-light)' : '#fff',
    }}>
      <span style={{
        width: 20, height: 20, borderRadius: 5, flexShrink: 0, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 13, color: '#fff',
        background: checked ? 'var(--blue)' : '#fff', border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border2)'}`,
      }}>{checked ? '✓' : ''}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{title}</div>
        {sub && <div style={{ fontSize: 12, color: 'var(--text3)' }}>{sub}</div>}
      </div>
      {right}
    </div>
  )
}

export default function QueryFlow() {
  const navigate = useNavigate()
  const [stap, setStap] = useState(0)
  const [profielen, setProfielen] = useState([])
  const [aanbieders, setAanbieders] = useState([])
  const [profielKey, setProfielKey] = useState(null)
  const [indicatoren, setIndicatoren] = useState([])
  const [gekozenInd, setGekozenInd] = useState([])
  const [gekozenZa, setGekozenZa] = useState([])
  const [bezig, setBezig] = useState(false)
  const [fout, setFout] = useState(null)

  useEffect(() => {
    listProfielen().then(setProfielen).catch(e => setFout(e.message))
    listZorgaanbieders().then(setAanbieders).catch(e => setFout(e.message))
  }, [])

  async function kiesProfiel(key) {
    setProfielKey(key); setFout(null)
    const p = await getProfiel(key)
    setIndicatoren(p.indicatoren)
    setGekozenInd(p.indicatoren.map(i => i.code))   // standaard alles aangevinkt
    setStap(1)
  }

  function toggle(list, set, val) {
    set(list.includes(val) ? list.filter(x => x !== val) : [...list, val])
  }

  async function versturen() {
    setBezig(true); setFout(null)
    try {
      const u = await createUitvraag({
        profiel_key: profielKey, indicator_codes: gekozenInd, zorgaanbieder_ids: gekozenZa,
      })
      navigate(`/resultaten?uitvraag=${u.id}`)
    } catch (e) {
      setFout(e.message); setBezig(false)
    }
  }

  const profiel = profielen.find(p => p.key === profielKey)

  return (
    <Page>
      <PageTitle badge="Opvragen"
        title="🔎 Indicatoren opvragen"
        sub="Stel een gevalideerde uitvraag samen via een uitwisselprofiel en richt die op één of meer zorgaanbieders. Hun datastation berekent de antwoorden." />
      <Stepper stap={stap} />
      {fout && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}>
        <span style={{ color: 'var(--red)', fontSize: 14 }}>{fout}</span></Card>}

      {stap === 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {profielen.map(p => (
            <Card key={p.key} onClick={() => kiesProfiel(p.key)} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{p.label}</div>
              <div style={{ fontSize: 12, color: 'var(--text3)' }}>{p.afnemer}</div>
              <span style={{ alignSelf: 'flex-start', marginTop: 4, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, background: 'var(--blue-light)', color: 'var(--blue)' }}>
                {p.aantal_indicatoren} indicatoren</span>
            </Card>
          ))}
        </div>
      )}

      {stap === 1 && (
        <Card>
          <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 14 }}>Profiel: <b style={{ color: 'var(--text)' }}>{profiel?.label}</b> — kies de indicatoren.</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
            {indicatoren.map(i => (
              <SelectRow key={i.code} checked={gekozenInd.includes(i.code)}
                onToggle={() => toggle(gekozenInd, setGekozenInd, i.code)}
                title={i.label} sub={i.code}
                right={<span style={{ fontSize: 12, color: 'var(--text3)' }}>{i.eenheid}</span>} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <BtnGhost onClick={() => setStap(0)}>← Terug</BtnGhost>
            <BtnPrimary disabled={!gekozenInd.length} onClick={() => setStap(2)}>Verder ({gekozenInd.length})</BtnPrimary>
          </div>
        </Card>
      )}

      {stap === 2 && (
        <Card>
          <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 14 }}>Kies één of meer geregistreerde zorgaanbieders.</div>
          {aanbieders.length === 0 && <div style={{ fontSize: 14, color: 'var(--amber)', marginBottom: 14 }}>Nog geen zorgaanbieders geregistreerd. Voeg ze toe via de pagina Zorgaanbieders.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
            {aanbieders.map(z => (
              <SelectRow key={z.id} checked={gekozenZa.includes(z.id)}
                onToggle={() => toggle(gekozenZa, setGekozenZa, z.id)}
                title={z.naam} sub={[z.plaats, z.heeft_datastation ? 'eigen datastation' : 'gesimuleerd datastation'].filter(Boolean).join(' · ')} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <BtnGhost onClick={() => setStap(1)}>← Terug</BtnGhost>
            <BtnPrimary disabled={!gekozenZa.length} onClick={() => setStap(3)}>Verder ({gekozenZa.length})</BtnPrimary>
          </div>
        </Card>
      )}

      {stap === 3 && (
        <Card>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 14 }}>Samenvatting</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14, color: 'var(--text2)', marginBottom: 18 }}>
            <div>Uitwisselprofiel: <b>{profiel?.label}</b></div>
            <div>Indicatoren: <b>{gekozenInd.length}</b></div>
            <div>Zorgaanbieders: <b>{gekozenZa.length}</b></div>
            <div style={{ color: 'var(--text3)', fontSize: 13 }}>Er worden {gekozenInd.length * gekozenZa.length} vragen naar de datastations gestuurd.</div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <BtnGhost onClick={() => setStap(2)} disabled={bezig}>← Terug</BtnGhost>
            <BtnPrimary onClick={versturen} disabled={bezig}>{bezig ? 'Versturen…' : 'Uitvraag versturen'}</BtnPrimary>
          </div>
        </Card>
      )}
    </Page>
  )
}
