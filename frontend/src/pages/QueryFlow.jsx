import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Page, PageTitle, Card, BtnPrimary, BtnGhost, StatusPill } from '../components/UI'
import { listProfielen, getProfiel, getAanbiedersVoorProfiel, createUitvraag } from '../services/api'

const STAPPEN = ['Uitwisselprofiel', 'Indicatoren', 'Zorgaanbieders', 'Versturen']

function Badge({ tekst, kleur, size = 44 }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: 12, flexShrink: 0, background: kleur || 'var(--blue)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontWeight: 800, fontSize: tekst && tekst.length > 3 ? 12 : 15, letterSpacing: '.02em',
    }}>{tekst}</span>
  )
}

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

function MetaRow({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13.5, color: 'var(--text2)', lineHeight: 1.5 }}>{children}</div>
    </div>
  )
}

export default function QueryFlow() {
  const navigate = useNavigate()
  const [stap, setStap] = useState(0)
  const [profielen, setProfielen] = useState([])
  const [capAanbieders, setCapAanbieders] = useState([])
  const [inclNietProd, setInclNietProd] = useState(false)
  const [capLaden, setCapLaden] = useState(false)
  const [profielKey, setProfielKey] = useState(null)
  const [detail, setDetail] = useState(null)   // volledig uitwisselprofiel
  const [gekozenInd, setGekozenInd] = useState([])
  const [gekozenZa, setGekozenZa] = useState([])
  const [openSparql, setOpenSparql] = useState(null)
  const [bezig, setBezig] = useState(false)
  const [fout, setFout] = useState(null)

  useEffect(() => {
    listProfielen().then(setProfielen).catch(e => setFout(e.message))
  }, [])

  // Capabilities laden zodra een profiel is gekozen (of de toggle wijzigt)
  useEffect(() => {
    if (!profielKey) return
    setCapLaden(true)
    getAanbiedersVoorProfiel(profielKey, inclNietProd)
      .then(d => { setCapAanbieders(d.aanbieders); setGekozenZa([]) })
      .catch(e => setFout(e.message))
      .finally(() => setCapLaden(false))
  }, [profielKey, inclNietProd])

  async function kiesProfiel(key) {
    setProfielKey(key); setFout(null)
    const p = await getProfiel(key)
    setDetail(p)
    setGekozenInd(p.indicatoren.map(i => i.code))
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
    } catch (e) { setFout(e.message); setBezig(false) }
  }

  const profiel = profielen.find(p => p.key === profielKey)

  return (
    <Page>
      <PageTitle badge="Opvragen" title="🔎 Indicatoren opvragen"
        sub="Stel een gevalideerde uitvraag samen via een uitwisselprofiel en richt die op één of meer zorgaanbieders. Hun datastation berekent de antwoorden." />
      <Stepper stap={stap} />
      {fout && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}>
        <span style={{ color: 'var(--red)', fontSize: 14 }}>{fout}</span></Card>}

      {stap === 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {profielen.map(p => (
            <Card key={p.key} onClick={() => kiesProfiel(p.key)}
              style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <Badge tekst={p.badge} kleur={p.kleur} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3 }}>{p.label}</div>
                <div style={{ fontSize: 12.5, color: 'var(--text3)', margin: '2px 0 10px' }}>{p.afnemer}</div>
                <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, background: 'var(--blue-light)', color: 'var(--blue)' }}>
                  {p.aantal_indicatoren} indicatoren
                </span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {stap === 1 && detail && (
        <>
          {/* Volledig uitwisselprofiel */}
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 16 }}>
              <Badge tekst={detail.badge} kleur={detail.kleur} />
              <div>
                <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)' }}>{detail.label}</div>
                <div style={{ fontSize: 13, color: 'var(--text3)' }}>{detail.afnemer} · uitwisselprofiel v{detail.versie}</div>
              </div>
            </div>
            {detail.analyse_vraag && (
              <div style={{ marginBottom: 16 }}>
                <MetaRow label="Analyse-vraag"><i>"{detail.analyse_vraag}"</i></MetaRow>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
              {detail.grondslag && <MetaRow label="Juridische grondslag">{detail.grondslag}</MetaRow>}
              {detail.doelbinding && <MetaRow label="Doelbinding">{detail.doelbinding}</MetaRow>}
              {detail.autorisatie && <MetaRow label="Autorisatie">{detail.autorisatie}</MetaRow>}
              {detail.terugkoppeling && <MetaRow label="Terugkoppeling">{detail.terugkoppeling}</MetaRow>}
              {detail.bron && <MetaRow label="Bron"><a href={detail.bron} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>uitwisselprofiel-repository ↗</a></MetaRow>}
            </div>
          </Card>

          {/* Indicatoren kiezen */}
          <Card>
            <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 14 }}>Kies de gevalideerde indicatoren die je wilt uitvragen.</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 18 }}>
              {detail.indicatoren.map(i => {
                const checked = gekozenInd.includes(i.code)
                const open = openSparql === i.code
                return (
                  <div key={i.code} style={{ border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border)'}`, borderRadius: 'var(--radius)', background: checked ? 'var(--blue-light)' : '#fff', overflow: 'hidden' }}>
                    <div onClick={() => toggle(gekozenInd, setGekozenInd, i.code)} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 14px', cursor: 'pointer' }}>
                      <span style={{ width: 20, height: 20, borderRadius: 5, flexShrink: 0, marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#fff', background: checked ? 'var(--blue)' : '#fff', border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border2)'}` }}>{checked ? '✓' : ''}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{i.label}</span>
                          <span style={{ fontSize: 12, color: 'var(--text3)', whiteSpace: 'nowrap' }}>{i.eenheid}</span>
                        </div>
                        {i.definitie && <div style={{ fontSize: 12.5, color: 'var(--text3)', marginTop: 3, lineHeight: 1.45 }}>{i.definitie}</div>}
                        {i.sparql && (
                          <button onClick={(e) => { e.stopPropagation(); setOpenSparql(open ? null : i.code) }}
                            style={{ marginTop: 6, background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--blue)', fontFamily: 'var(--font)' }}>
                            {open ? '− SPARQL verbergen' : '+ SPARQL tonen'}
                          </button>
                        )}
                      </div>
                    </div>
                    {open && i.sparql && (
                      <pre style={{ margin: 0, padding: '12px 16px', background: '#0f1a30', color: '#cfe2f3', fontSize: 12, lineHeight: 1.5, overflowX: 'auto', borderTop: '1px solid var(--border)' }}>{i.sparql}</pre>
                    )}
                  </div>
                )
              })}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <BtnGhost onClick={() => setStap(0)}>← Terug</BtnGhost>
              <BtnPrimary disabled={!gekozenInd.length} onClick={() => setStap(2)}>Verder ({gekozenInd.length})</BtnPrimary>
            </div>
          </Card>
        </>
      )}

      {stap === 2 && (
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: 14, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 13, color: 'var(--text3)', maxWidth: 520 }}>
              Alleen aanbieders die <b>{profiel?.label}</b> hebben geïmplementeerd. Standaard tonen we
              alleen status <b>productie</b> — de overige worden weggefilterd om uitvragen naar
              niet-compatibele aanbieders te voorkomen.
            </div>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text2)', whiteSpace: 'nowrap', cursor: 'pointer' }}>
              <input type="checkbox" checked={inclNietProd} onChange={e => setInclNietProd(e.target.checked)} />
              Ook test/implementatie tonen
            </label>
          </div>

          {capLaden ? (
            <div style={{ fontSize: 14, color: 'var(--text3)', padding: '8px 0' }}>Aanbieders laden…</div>
          ) : capAanbieders.length === 0 ? (
            <div style={{ fontSize: 14, color: 'var(--amber)', marginBottom: 14 }}>
              Geen aanbieders met dit profiel{inclNietProd ? '' : ' in productie'}. {inclNietProd ? 'Mogelijk is het profiel nergens geïmplementeerd.' : 'Zet de schakelaar aan om test/implementatie te zien.'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
              {capAanbieders.map(a => {
                const id = a.zorgaanbieder_id
                const selectbaar = a.geregistreerd && !!id
                const checked = selectbaar && gekozenZa.includes(id)
                return (
                  <div key={a.aanbieder_naam + a.versie}
                    onClick={() => selectbaar && toggle(gekozenZa, setGekozenZa, id)}
                    title={selectbaar ? '' : 'Niet geregistreerd in dit platform — wel in de registry'}
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
                      cursor: selectbaar ? 'pointer' : 'not-allowed', opacity: selectbaar ? 1 : 0.55,
                      borderRadius: 'var(--radius)', border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border)'}`,
                      background: checked ? 'var(--blue-light)' : '#fff' }}>
                    <span style={{ width: 20, height: 20, borderRadius: 5, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#fff', background: checked ? 'var(--blue)' : '#fff', border: `1.5px solid ${checked ? 'var(--blue)' : 'var(--border2)'}` }}>{checked ? '✓' : ''}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{a.aanbieder_naam}</div>
                      <div style={{ fontSize: 12, color: 'var(--text3)' }}>{[a.software_leverancier, `versie ${a.versie}`, selectbaar ? null : 'niet geregistreerd'].filter(Boolean).join(' · ')}</div>
                    </div>
                    <StatusPill status={a.status} />
                  </div>
                )
              })}
            </div>
          )}
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
