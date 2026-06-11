import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Nav } from './components/UI'
import { login as apiLogin, getMe, clearAuthToken } from './services/api'
import LoginScreen    from './pages/LoginScreen'
import Home           from './pages/Home'
import QueryFlow      from './pages/QueryFlow'
import Zorgaanbieders from './pages/Zorgaanbieders'
import Results        from './pages/Results'
import Analyse        from './pages/Analyse'
import Dekking        from './pages/Dekking'
import Gebruikersbeheer from './pages/Gebruikersbeheer'
import Organisaties   from './pages/Organisaties'
import NotFound       from './pages/NotFound'

const KIK_ENV = import.meta.env.VITE_KIK_ENV

function EnvBanner() {
  if (KIK_ENV !== 'staging') return null
  return (
    <div style={{
      background: '#f59e0b', color: '#1a2847', textAlign: 'center',
      fontSize: 13, fontWeight: 700, padding: '6px 12px', letterSpacing: '.03em',
    }}>
      STAGING-OMGEVING — testdata, niet voor productiegebruik
    </div>
  )
}

export default function App() {
  const [authUser, setAuthUser] = useState(null)
  const [booting, setBooting]   = useState(false)

  useEffect(() => {
    const onUnauth = () => setAuthUser(null)
    window.addEventListener('rhadix:unauthorized', onUnauth)
    return () => window.removeEventListener('rhadix:unauthorized', onUnauth)
  }, [])

  async function handleLogin(email, password) {
    await apiLogin(email, password)       // zet token in api-laag
    const me = await getMe()
    setAuthUser({ ...me, name: me.full_name || me.email })
  }

  function handleLogout() {
    clearAuthToken()
    setAuthUser(null)
  }

  if (!authUser) return (<><EnvBanner /><LoginScreen onLogin={handleLogin} /></>)

  const isPlatform = authUser.role === 'PLATFORM_ADMIN'
  const isAdmin    = isPlatform || authUser.role === 'ORG_ADMIN'

  const navLinks = [
    { to: '/opvragen',      label: 'Opvragen' },
    { to: '/zorgaanbieders', label: 'Zorgaanbieders' },
    { to: '/resultaten',    label: 'Resultaten' },
    { to: '/analyse',       label: 'Analyse' },
    { to: '/dekking',       label: 'Dekking' },
    ...(isAdmin    ? [{ to: '/gebruikers',   label: 'Gebruikers' }] : []),
    ...(isPlatform ? [{ to: '/organisaties', label: 'Organisaties' }] : []),
  ]

  return (
    <>
      <EnvBanner />
      <Nav authUser={authUser} onLogout={handleLogout} links={navLinks} />
      <Routes>
        <Route path="/" element={<Home authUser={authUser} />} />
        <Route path="/opvragen" element={<QueryFlow />} />
        <Route path="/zorgaanbieders" element={<Zorgaanbieders />} />
        <Route path="/resultaten" element={<Results />} />
        <Route path="/analyse" element={<Analyse />} />
        <Route path="/dekking" element={<Dekking authUser={authUser} />} />
        <Route path="/gebruikers" element={isAdmin ? <Gebruikersbeheer authUser={authUser} /> : <Navigate to="/" replace />} />
        <Route path="/organisaties" element={isPlatform ? <Organisaties /> : <Navigate to="/" replace />} />
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  )
}
