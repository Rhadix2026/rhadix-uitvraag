import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Nav } from './components/UI'
import { setAuthToken, clearAuthToken } from './services/api'
import LoginScreen   from './pages/LoginScreen'
import Home          from './pages/Home'
import QueryFlow     from './pages/QueryFlow'
import Registration  from './pages/Registration'
import Results       from './pages/Results'
import NotFound      from './pages/NotFound'

const NAV_LINKS = [
  { to: '/opvragen', label: 'Opvragen' },
  { to: '/beheer',   label: 'Beheer' },
  { to: '/resultaten', label: 'Resultaten' },
]

export default function App() {
  const [authUser, setAuthUser] = useState(null)

  // Logout bij 401 vanuit de API-laag
  useEffect(() => {
    const onUnauth = () => setAuthUser(null)
    window.addEventListener('kik:unauthorized', onUnauth)
    return () => window.removeEventListener('kik:unauthorized', onUnauth)
  }, [])

  async function handleLogin(email /*, password */) {
    // Demo-auth: nog geen backend-authenticatie in deze shell.
    setAuthToken('demo-token')
    setAuthUser({ email, name: email.split('@')[0] })
  }

  function handleLogout() {
    clearAuthToken()
    setAuthUser(null)
  }

  if (!authUser) return <LoginScreen onLogin={handleLogin} />

  return (
    <>
      <Nav authUser={authUser} onLogout={handleLogout} links={NAV_LINKS} />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/opvragen" element={<QueryFlow />} />
        <Route path="/beheer" element={<Registration />} />
        <Route path="/resultaten" element={<Results />} />
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  )
}
