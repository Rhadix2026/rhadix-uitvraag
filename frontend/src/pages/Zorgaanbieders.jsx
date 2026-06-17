import { useEffect, useMemo, useRef, useState } from 'react'
import { Page, PageTitle, Card, BtnPrimary, Field, Modal } from '../components/UI'
import { listZorgaanbieders, registerZorgaanbieder, getZorgaanbieder, importZorgaanbieders } from '../services/api'

function FaseBadge({ fase }) {
  if (!fase) return <span style={{ color: 'var(--text3)' }}>—</span>
  const groen = /fase\s*[3-9]|fase\s*2\.2/i.test(fase)
  const grijs = /niet betrokken|fase\s*0/i.test(fase)
  const c = grijs ? 'var(--text3)' : groen ? 'var(--green)' : 'var(--amber)'
  const bg = grijs ? 'var(--bg)' : groen ? 'var(--green-light)' : 'var(--amber-light, #fef3c7)'
  return <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, background: bg, color: c }}>{fase}</span>
}

export default function Zorgaanbieders() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [fout, setFout] = useState(null)
  const [form, setForm] = useState({ naam: '', plaats: '', kvk: '', contact_email: '', datastation_url: '' })
  const [bezig, setBezig] = useState(false)
  const [zoek, setZoek] = useState('')
  const [detail, setDetail] = useState(null)
  const [importInfo, setImportInfo] = useState(null)
  const fileRef = useRef(null)

  function laden() { listZorgaanbieders().then(setRows).catch(e => setFout(e.message)) }
  useEffect(laden, [])

  const gefilterd = useMemo(() => {
    const q = zoek.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(z => [z.naam, z.plaats, z.gemeente, z.kvk, z.daas_leverancier, z.huidige_fase, z.sectoren]
      .some(v => (v || '').toLowerCase().includes(q)))
  }, [rows, zoek])

  async function opslaan() {
    setBezig(true); setFout(null)
    try {
      await registerZorgaanbieder({
        naam: form.naam, plaats: form.plaats || null, kvk: form.kvk || null,
        contact_email: form.contact_email || null, datastation_url: form.datastation_url || null,
      })
      setOpen(false); setForm({ naam: '', plaats: '', kvk: '', contact_email: '', datastation_url: '' }); laden()
    } catch (e) { setFout(e.message) } finally { setBezig(false) }
  }

  async function csvGekozen(e) {
    const f = e.target.files?.[0]; if (!f) return
    setBezig(true); setFout(null); setImportInfo(null)
    try { const r = await importZorgaanbieders(f); setImportInfo(r); laden() }
    catch (err) { setFout(err.message) } finally { setBezig(false); if (fileRef.current) fileRef.current.value = '' }
  }

  async function toonDetail(id) {
    setDetail({ laden: true })
    try { setDetail(await getZorgaanbieder(id)) } catch (e) { setFout(e.message); setDetail(null) }
  }

  return (
    <Page>
      <PageTitle badge="Zorgaanbieders"
        title="🏥 Zorgaanbieders"
        sub="Zorgaanbieders die met KIK-V werken of gaan werken. Ketenpartijen kiezen hieruit bij het opvragen van indicatoren." />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input value={zoek} onChange={e => setZoek(e.target.value)} placeholder="Zoek op naam, plaats, KvK, software, fase…"
          style={{ flex: 1, minWidth: 260, padding: '9px 14px', borderRadius: 'var(--radius)', border: '1.5px solid var(--border)', fontSize: 14 }} />
        <span style={{ fontSize: 13, color: 'var(--text3)', whiteSpace: 'nowrap' }}>{gefilterd.length} van {rows.length}</span>
        <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={csvGekozen} style={{ display: 'none' }} />
        <BtnPrimary onClick={() => fileRef.current?.click()} disabled={bezig}>{bezig ? 'Bezig…' : '⬆ CSV importeren'}</BtnPrimary>
        <BtnPrimary onClick={() => setOpen(true)}>+ Registreren</BtnPrimary>
      </div>

      {importInfo && <Card style={{ marginBottom: 16, background: 'var(--green-light)', border: '1px solid var(--green)' }}>
        <span style={{ color: 'var(--green)', fontSize: 14 }}>✓ Import: {importInfo.aanbieders} aanbieders uit {importInfo.rijen} rijen — {importInfo.nieuw} nieuw, {importInfo.bijgewerkt} bijgewerkt. Totaal nu {importInfo.totaal_in_db}.</span></Card>}

      {fout && !open && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}>
        <span style={{ color: 'var(--red)', fontSize: 14 }}>{fout}</span></Card>}

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: 'var(--bg)', textAlign: 'left' }}>
              {['Naam', 'Plaats', 'KvK', 'Fase', 'Software', 'Profielen', 'Datastation'].map(h =>
                <th key={h} style={{ padding: '12px 16px', fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {gefilterd.map(z => (
              <tr key={z.id} onClick={() => toonDetail(z.id)} style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}>
                <td style={{ padding: '11px 16px', fontWeight: 600, color: 'var(--text)' }}>
                  {z.naam}
                  {z.heeft_credential === 'Ja' && <span title="Heeft Verifiable Credential" style={{ marginLeft: 6, fontSize: 11 }}>🔐</span>}
                </td>
                <td style={{ padding: '11px 16px', color: 'var(--text2)' }}>{z.plaats || '—'}</td>
                <td style={{ padding: '11px 16px', color: 'var(--text2)' }}>{z.kvk || '—'}</td>
                <td style={{ padding: '11px 16px' }}><FaseBadge fase={z.huidige_fase} /></td>
                <td style={{ padding: '11px 16px', color: 'var(--text2)' }}>{z.daas_leverancier || '—'}</td>
                <td style={{ padding: '11px 16px', color: 'var(--text2)', textAlign: 'center' }}>{z.aantal_profielen || 0}</td>
                <td style={{ padding: '11px 16px' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99,
                    background: z.heeft_datastation ? 'var(--green-light)' : 'var(--bg)',
                    color: z.heeft_datastation ? 'var(--green)' : 'var(--text3)' }}>
                    {z.heeft_datastation ? 'Eigen endpoint' : 'Gesimuleerd'}</span>
                </td>
              </tr>
            ))}
            {gefilterd.length === 0 && <tr><td colSpan={7} style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>Geen zorgaanbieders gevonden.</td></tr>}
          </tbody>
        </table>
      </Card>

      {open && (
        <Modal title="Zorgaanbieder registreren" onClose={() => setOpen(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {fout && <div style={{ color: 'var(--red)', fontSize: 13 }}>{fout}</div>}
            <Field label="Naam" required value={form.naam} onChange={v => setForm({ ...form, naam: v })} placeholder="Zorggroep …" />
            <Field label="Plaats" value={form.plaats} onChange={v => setForm({ ...form, plaats: v })} />
            <Field label="KvK-nummer" value={form.kvk} onChange={v => setForm({ ...form, kvk: v })} />
            <Field label="Contact-e-mail" type="email" value={form.contact_email} onChange={v => setForm({ ...form, contact_email: v })} />
            <Field label="Datastation-URL (SPARQL, optioneel)" value={form.datastation_url} onChange={v => setForm({ ...form, datastation_url: v })} placeholder="Leeg = gesimuleerd datastation" />
            <BtnPrimary disabled={!form.naam.trim() || bezig} onClick={opslaan}>{bezig ? 'Opslaan…' : 'Registreren'}</BtnPrimary>
          </div>
        </Modal>
      )}

      {detail && (
        <Modal title={detail.laden ? 'Laden…' : detail.naam} onClose={() => setDetail(null)}>
          {detail.laden ? <div style={{ color: 'var(--text3)' }}>Laden…</div> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, fontSize: 14, maxWidth: 560 }}>
              <DetailBlok titel="Algemeen" velden={[
                ['KvK', detail.kvk], ['Adres', [detail.straatnaam, detail.huisnummer].filter(Boolean).join(' ')],
                ['Postcode / plaats', [detail.postcode, detail.plaats].filter(Boolean).join('  ')],
                ['Gemeente', detail.gemeente], ['Samenwerkingsverband', detail.samenwerkingsverband],
                ['Verifiable Credential', detail.heeft_credential], ['Sectoren', detail.sectoren],
                ['Doelgroepen', detail.doelgroepen], ['Zorgkantoren', detail.zorgkantoren],
                ['Concessiehouders', detail.concessiehouders],
              ]} />
              <DetailBlok titel="Contactpersoon" velden={[
                ['Naam', [detail.contact_voornaam, detail.contact_achternaam].filter(Boolean).join(' ')],
                ['Functie', detail.contact_functie], ['E-mail', detail.contact_email], ['Telefoon', detail.contact_telefoon],
              ]} />
              <DetailBlok titel="Capaciteit" velden={[
                ['FTE', detail.fte], ['Locaties', detail.locaties], ['Bedden', detail.bedden],
              ]} />
              <DetailBlok titel="Implementatie" velden={[
                ['Huidige fase', detail.huidige_fase], ['DAAS-leverancier', detail.daas_leverancier],
                ['Consultant', detail.implementatie_consultant], ['Implementatiepartner', detail.implementatiepartner],
                ['Zelfscan retour', detail.zelfscan_retour], ['Intentieverklaring', detail.intentieverklaring],
                ['Contract datastation', detail.contract_datastation],
                ['Aangesloten test', detail.aangesloten_test], ['Aangesloten productie', detail.aangesloten_productie],
              ]} />
              <DetailBlok titel="Uitwisselprofielen" velden={[['Profielen', detail.uitwisselprofielen]]} />
              <DetailBlok titel="Vestigingen" velden={[['Vestigingen', detail.vestigingen]]} />
            </div>
          )}
        </Modal>
      )}
    </Page>
  )
}

function DetailBlok({ titel, velden }) {
  const zichtbaar = velden.filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (zichtbaar.length === 0) return null
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 6 }}>{titel}</div>
      <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 4, columnGap: 12 }}>
        {zichtbaar.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <div style={{ color: 'var(--text3)' }}>{k}</div>
            <div style={{ color: 'var(--text)' }}>{String(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
