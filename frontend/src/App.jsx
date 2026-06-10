import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Nav } from './components/UI'
import { login as apiLogin, getMe, clearAuthToken } from './services/api'
import LoginScreen    from './pages/LoginScreen'
import Home           from './pages/Home'
import QueryFlow      from './pages/QueryFlow'
import Zorgaanbieders from './pages/Zorgaanbieders'
import Results        from './pages/Results'
import Gebruikersbeheer from './pages/Gebruikersbeheer'
import Organisaties   from './pages/Organisaties'
import NotFound       from './pages/NotFound'

export default function App() {
  const [authUser, setAuthUser] = useState(null)
  const [booting, setBooting]   = useState(false)

  useEffect(() => {
    const onUnauth = () => setAuthUser(null)
    window.addEventListener('kik:unauthorized', onUnauth)
    return () => window.removeEventListener('kik:unauthorized', onUnauth)
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

  if (!authUser) return <LoginScreen onLogin={handleLogin} />

  const isPlatform = authUser.role === 'PLATFORM_ADMIN'
  const isAdmin    = isPlatform || authUser.role === 'ORG_ADMIN'

  const navLinks = [
    { to: '/opvragen',      label: 'Opvragen' },
    { to: '/zorgaanbieders', label: 'Zorgaanbieders' },
    { to: '/resultaten',    label: 'Resultaten' },
    ...(isAdmin    ? [{ to: '/gebruikers',   label: 'Gebruikers' }] : []),
    ...(isPlatform ? [{ to: '/organisaties', label: 'Organisaties' }] : []),
  ]

  return (
    <>
      <Nav authUser={authUser} onLogout={handleLogout} links={navLinks} />
      <Routes>
        <Route path="/" element={<Home authUser={authUser} />} />
        <Route path="/opvragen" element={<QueryFlow />} />
        <Route path="/zorgaanbieders" element={<Zorgaanbieders />} />
        <Route path="/resultaten" element={<Results />} />
        <Route path="/gebruikers" element={isAdmin ? <Gebruikersbeheer authUser={authUser} /> : <Navigate to="/" replace />} />
        <Route path="/organisaties" element={isPlatform ? <Organisaties /> : <Navigate to="/" replace />} />
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  )
}
