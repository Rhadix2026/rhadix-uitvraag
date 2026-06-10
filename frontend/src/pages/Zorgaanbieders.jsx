import { useEffect, useState } from 'react'
import { Page, PageTitle, Card, BtnPrimary, Field, Modal } from '../components/UI'
import { listZorgaanbieders, registerZorgaanbieder } from '../services/api'

export default function Zorgaanbieders() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [fout, setFout] = useState(null)
  const [form, setForm] = useState({ naam: '', plaats: '', kvk: '', contact_email: '', datastation_url: '' })
  const [bezig, setBezig] = useState(false)

  function laden() { listZorgaanbieders().then(setRows).catch(e => setFout(e.message)) }
  useEffect(laden, [])

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

  return (
    <Page>
      <PageTitle badge="Zorgaanbieders"
        title="🏥 Zorgaanbieders"
        sub="Zorgaanbieders registreren zich hier om uitvragen te kunnen ontvangen. Ketenpartijen kiezen vervolgens uit deze lijst bij het opvragen van indicatoren." />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: 'var(--text3)' }}>{rows.length} geregistreerd</span>
        <BtnPrimary onClick={() => setOpen(true)}>+ Zorgaanbieder registreren</BtnPrimary>
      </div>

      {fout && !open && <Card style={{ marginBottom: 16, background: 'var(--red-light)', border: '1px solid var(--red)' }}>
        <span style={{ color: 'var(--red)', fontSize: 14 }}>{fout}</span></Card>}

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ background: 'var(--bg)', textAlign: 'left' }}>
              {['Naam', 'Plaats', 'KvK', 'Contact', 'Datastation'].map(h =>
                <th key={h} style={{ padding: '12px 16px', fontSize: 12, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(z => (
              <tr key={z.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--text)' }}>{z.naam}</td>
                <td style={{ padding: '12px 16px', color: 'var(--text2)' }}>{z.plaats || '—'}</td>
                <td style={{ padding: '12px 16px', color: 'var(--text2)' }}>{z.kvk || '—'}</td>
                <td style={{ padding: '12px 16px', color: 'var(--text2)' }}>{z.contact_email || '—'}</td>
                <td style={{ padding: '12px 16px' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99,
                    background: z.heeft_datastation ? 'var(--green-light)' : 'var(--bg)',
                    color: z.heeft_datastation ? 'var(--green)' : 'var(--text3)' }}>
                    {z.heeft_datastation ? 'Eigen endpoint' : 'Gesimuleerd'}</span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>Nog geen zorgaanbieders geregistreerd.</td></tr>}
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
    </Page>
  )
}
