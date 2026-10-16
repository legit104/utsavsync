import { useEffect, useState } from 'react'
import VisitorDashboard from './VisitorDashboard'
import './App.css'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY
const hasAuth = Boolean(supabaseUrl && supabaseKey)

async function authRequest(path, payload) {
  const response = await fetch(`${supabaseUrl}/auth/v1/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', apikey: supabaseKey },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.msg || data.message || data.error_description || 'Unable to complete sign in.')
  return data
}

function App() {
  const [role, setRole] = useState('visitor')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [mode, setMode] = useState('signin')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem('utsavsync-session') || 'null') } catch { return null }
  })

  useEffect(() => {
    if (!remember && session) localStorage.removeItem('utsavsync-session')
  }, [remember, session])

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      if (!hasAuth) {
        const demo = { access_token: null, user: { email, user_metadata: { role } }, demo: true }
        setSession(demo)
        if (remember) localStorage.setItem('utsavsync-session', JSON.stringify(demo))
        setMessage('Demo session started. Connect Supabase to enable real accounts.')
      } else if (mode === 'signup') {
        const data = await authRequest('signup', { email, password, data: { role } })
        if (data.access_token) {
          setSession(data)
          if (remember) localStorage.setItem('utsavsync-session', JSON.stringify(data))
        } else {
          setMode('signin')
          setMessage('Account created. Check your email to confirm, then sign in.')
        }
      } else {
        const data = await authRequest('token?grant_type=password', { email, password })
        setSession(data)
        if (remember) localStorage.setItem('utsavsync-session', JSON.stringify(data))
      }
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function forgotPassword() {
    if (!email) { setMessage('Enter your email address first.'); return }
    if (!hasAuth) { setMessage('Password recovery is available after Supabase is configured.'); return }
    setBusy(true)
    try {
      await authRequest('recover', { email })
      setMessage('Password reset instructions have been sent to your email.')
    } catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }

  function signOut() {
    setSession(null)
    localStorage.removeItem('utsavsync-session')
    setPassword('')
    setMessage('')
  }

  if (session) {
    return <VisitorDashboard onBackToLogin={signOut} userEmail={session.user?.email} userRole={session.user?.user_metadata?.role || 'visitor'} session={session} />
  }

  const isSignup = mode === 'signup'
  return (
    <main className="login-page">
      <div className="login-art" aria-hidden="true" />
      <section className="auth-panel" aria-label={isSignup ? 'Create UtsavSync account' : 'Sign in to UtsavSync'}>
        <div className="auth-heading">
          <span className="auth-mark">✺</span>
          <p className="auth-kicker">CELEBRATE TOGETHER</p>
          <h1>{isSignup ? 'Join UtsavSync' : 'Welcome back'}</h1>
          <p>{isSignup ? 'Create your account to help keep celebrations safe and clean.' : 'Sign in to help keep Mumbai’s festivals safe and clean.'}</p>
        </div>
        <div className="role-cards" role="group" aria-label="Choose your role">
          <button type="button" className={`role-card visitor-card ${role === 'visitor' ? 'active' : ''}`} onClick={() => setRole('visitor')}>
            <span className="role-emoji">🪔</span><strong>Visitor</strong><small>Join &amp; explore</small>
          </button>
          <button type="button" className={`role-card volunteer-card ${role === 'volunteer' ? 'active' : ''}`} onClick={() => setRole('volunteer')}>
            <span className="role-emoji">🤝</span><strong>Volunteer</strong><small>Report &amp; support</small>
          </button>
        </div>
        <p className="role-hint">{!hasAuth
          ? 'Prototype demo: choose a role, then sign in to open that workspace.'
          : isSignup
            ? 'Choose Volunteer when creating your account if you will help with site operations.'
            : 'Sign in opens the role already assigned to your account.'}</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="auth-email">Email address</label>
          <input id="auth-email" type="email" placeholder="you@example.com" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required />
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" placeholder={isSignup ? 'Create a password (6+ characters)' : 'Enter your password'} autoComplete={isSignup ? 'new-password' : 'current-password'} minLength={6} value={password} onChange={event => setPassword(event.target.value)} required />
          <div className="auth-options">
            <label className="remember-label"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} /> Remember me</label>
            {!isSignup && <button type="button" className="link-button" onClick={forgotPassword} disabled={busy}>Forgot password?</button>}
          </div>
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'} <span>→</span></button>
          {message && <p className="auth-message" role="status">{message}</p>}
        </form>
        <div className="auth-switch"><span>{isSignup ? 'Already have an account?' : 'New to UtsavSync?'}</span><button className="link-button" type="button" onClick={() => { setMode(isSignup ? 'signin' : 'signup'); setMessage('') }}>{isSignup ? 'Sign in' : 'Create account'}</button></div>
        {!hasAuth && <p className="demo-note">Prototype mode · demo access enabled</p>}
      </section>
    </main>
  )
}

export default App
