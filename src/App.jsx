import { useEffect, useState } from 'react'
import VisitorDashboard from './VisitorDashboard'
import './App.css'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY
const hasAuth = Boolean(supabaseUrl && supabaseKey)

const SESSION_KEY = 'utsavsync-session'
const NOT_CONFIGURED = 'Accounts are not set up on this computer. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to the frontend .env, then restart npm run dev.'

/* Supabase's error messages, in words a festival visitor understands. */
const FRIENDLY_ERRORS = [
  [/invalid login credentials/i, 'Wrong email or password. If you are new, create an account first.'],
  [/email not confirmed/i, 'Please confirm your email first: open the link Supabase sent to your inbox, then sign in.'],
  [/user already registered/i, 'An account with this email already exists. Sign in instead.'],
  [/rate limit/i, 'Too many attempts or emails right now. Please wait a few minutes and try again.'],
]

async function authRequest(path, payload) {
  const response = await fetch(`${supabaseUrl}/auth/v1/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', apikey: supabaseKey },
    body: JSON.stringify(payload),
  })
  const data = await response.json()
  if (!response.ok) {
    const raw = data.msg || data.message || data.error_description || 'Unable to complete sign in.'
    throw new Error(FRIENDLY_ERRORS.find(([pattern]) => pattern.test(raw))?.[1] || raw)
  }
  return data
}

/* Only a real Supabase session counts; old demo sessions and anything unreadable are dropped. */
function loadStoredSession() {
  try {
    const stored = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
    if (hasAuth && stored?.access_token && stored?.refresh_token && !stored.demo) return stored
  } catch { /* fall through */ }
  localStorage.removeItem(SESSION_KEY)
  return null
}

function withExpiry(data) {
  return { ...data, expires_at: data.expires_at || Math.floor(Date.now() / 1000) + (data.expires_in || 3600) }
}

function App() {
  const [role, setRole] = useState('visitor')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [mode, setMode] = useState('signin')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [session, setSession] = useState(loadStoredSession)

  function startSession(data) {
    const next = withExpiry(data)
    setSession(next)
    if (remember) localStorage.setItem(SESSION_KEY, JSON.stringify(next))
    else localStorage.removeItem(SESSION_KEY)
  }

  useEffect(() => {
    if (!remember && session) localStorage.removeItem(SESSION_KEY)
  }, [remember, session])

  /* Supabase access tokens last about an hour: renew one a minute before it expires
     (or straight away if it already has), otherwise sign out. */
  useEffect(() => {
    if (!session?.refresh_token) return undefined
    const wait = Math.max(0, (session.expires_at - 60) * 1000 - Date.now())
    const timer = setTimeout(async () => {
      try {
        const data = await authRequest('token?grant_type=refresh_token', { refresh_token: session.refresh_token })
        const next = withExpiry(data)
        setSession(next)
        if (localStorage.getItem(SESSION_KEY)) localStorage.setItem(SESSION_KEY, JSON.stringify(next))
      } catch {
        setSession(null)
        localStorage.removeItem(SESSION_KEY)
        setMessage('Your session expired. Please sign in again.')
      }
    }, wait)
    return () => clearTimeout(timer)
  }, [session])

  async function handleSubmit(event) {
    event.preventDefault()
    setMessage('')
    if (!hasAuth) { setMessage(NOT_CONFIGURED); return }
    setBusy(true)
    try {
      if (mode === 'signup') {
        const data = await authRequest('signup', { email, password, data: { role } })
        if (data.access_token) {
          startSession(data)
        } else {
          setMode('signin')
          setPassword('')
          setMessage(`Account created. We sent a confirmation link to ${email}. Open it, then sign in here.`)
        }
      } else {
        startSession(await authRequest('token?grant_type=password', { email, password }))
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
    if (session?.access_token) {
      fetch(`${supabaseUrl}/auth/v1/logout`, {
        method: 'POST', headers: { apikey: supabaseKey, Authorization: `Bearer ${session.access_token}` },
      }).catch(() => {})
    }
    setSession(null)
    localStorage.removeItem(SESSION_KEY)
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
        {isSignup && (
          <div className="role-cards" role="group" aria-label="Choose your role">
            <button type="button" className={`role-card visitor-card ${role === 'visitor' ? 'active' : ''}`} onClick={() => setRole('visitor')}>
              <span className="role-emoji">🪔</span><strong>Visitor</strong><small>Join &amp; explore</small>
            </button>
            <button type="button" className={`role-card volunteer-card ${role === 'volunteer' ? 'active' : ''}`} onClick={() => setRole('volunteer')}>
              <span className="role-emoji">🤝</span><strong>Volunteer</strong><small>Report &amp; support</small>
            </button>
          </div>
        )}
        <p className="role-hint">{!hasAuth
          ? 'Accounts are not configured on this computer yet.'
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
        {!hasAuth && <p className="demo-note">Sign-in unavailable · Supabase is not configured</p>}
      </section>
    </main>
  )
}

export default App
