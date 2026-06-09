import { useState } from 'react'
import { KikLogo, KikMark } from '../components/Brand'

export default function LoginScreen({ onLogin }) {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      await onLogin(email.trim() || 'demo@kik-starter.nl', password)
    } catch (err) {
      setError('Inloggen mislukt')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    padding: '10px 14px', borderRadius: 'var(--radius)', border: '1.5px solid var(--border)',
    fontSize: 14, fontFamily: 'var(--font)', outline: 'none', background: '#fff',
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', background: 'var(--bg)' }}>
      {/* ── Links — branding ── */}
      <div style={{
        flex: 1, background: 'var(--blue-hero)', display: 'flex', flexDirection: 'column',
        position: 'relative', overflow: 'hidden',
      }}>
        <div style={{ padding: '32px 48px 0' }}><KikLogo /></div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 48px 100px' }}>
          <span style={{
            display: 'inline-flex', alignSelf: 'flex-start', background: 'rgba(111,168,208,.25)',
            color: 'rgba(168,197,224,.95)', fontSize: 11, fontWeight: 700, letterSpacing: '1.5px',
            padding: '5px 12px', borderRadius: 99, marginBottom: 24, textTransform: 'uppercase',
          }}>KIK-V · Rhadix editie</span>
          <h1 style={{ fontWeight: 800, fontSize: 36, color: '#fff', lineHeight: 1.2, letterSpacing: '-0.02em', marginBottom: 18, maxWidth: 460 }}>
            De KIK-V Starter,{' '}
            <span style={{ color: 'var(--accent)' }}>opnieuw opgebouwd</span>{' '}
            in de Rhadix-stack
          </h1>
          <p style={{ fontSize: 15, color: 'rgba(168,197,224,.8)', lineHeight: 1.65, maxWidth: 420 }}>
            Decentrale databronnen bevragen via uitwisselprofielen en SPARQL — in een
            moderne, vertrouwde omgeving.
          </p>
        </div>
        {/* decoratie rechtsonder */}
        <div style={{ position: 'absolute', bottom: -40, right: -30, opacity: 0.12, transform: 'scale(7)' }}>
          <KikMark size={40} />
        </div>
      </div>

      {/* ── Rechts — loginform ── */}
      <div style={{ width: 440, background: '#fff', display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '56px 48px', borderLeft: '1px solid var(--border)' }}>
        <div style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', marginBottom: 6 }}>Inloggen</h2>
          <p style={{ fontSize: 14, color: 'var(--text3)' }}>Voer uw gegevens in om door te gaan.</p>
        </div>

        <div style={{ background: 'var(--blue-light)', border: '1px solid var(--blue-mid)', borderRadius: 'var(--radius)', padding: '12px 14px', marginBottom: 20, fontSize: 13 }}>
          <div style={{ fontWeight: 700, color: 'var(--blue)', marginBottom: 4 }}>🎯 Demo-toegang</div>
          <div style={{ color: 'var(--text2)' }}>
            Deze shell heeft nog geen echte authenticatie — klik op <strong>Demo inloggen</strong> om de applicatie te verkennen.
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text2)' }}>E-mailadres</span>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="naam@organisatie.nl" style={inputStyle} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text2)' }}>Wachtwoord</span>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" style={inputStyle} />
          </label>
          {error && <div style={{ color: 'var(--red)', fontSize: 13 }}>{error}</div>}
          <button type="submit" disabled={loading} style={{
            background: 'var(--blue)', color: '#fff', border: 'none', borderRadius: 'var(--radius)',
            padding: '11px 20px', fontSize: 14, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font)', marginTop: 4,
          }}>{loading ? 'Bezig…' : 'Demo inloggen →'}</button>
        </form>
      </div>
    </div>
  )
}
