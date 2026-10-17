import { useEffect, useState } from 'react'
import VisitorDashboard from './VisitorDashboard'
import { api } from './api'
import { NOT_CONFIGURED, authConfigured, refreshSession, requestPasswordRecovery, signInWithPassword, signOutRemote, signUp } from './auth'
import { LocalizedText } from './i18n'
import './App.css'

const languageOptions = [['en', 'English'], ['hi', 'हिन्दी'], ['mr', 'मराठी']]
function savedLanguage() {
  const stored = window.localStorage.getItem('utsavsync-language')
  return ['en', 'hi', 'mr'].includes(stored) ? stored : 'en'
}

function readRememberedSession() {
  try {
    const session = JSON.parse(window.localStorage.getItem('utsavsync-session') || 'null')
    const realSession = session?.access_token && !session.demo
    const expiredVolunteerPass = session?.access_token?.startsWith('vs1.') && session.expires_at * 1000 <= Date.now()
    if (!realSession || expiredVolunteerPass || (!session.refresh_token && !session.access_token.startsWith('vs1.'))) {
      window.localStorage.removeItem('utsavsync-session')
      return null
    }
    return session
  } catch {
    window.localStorage.removeItem('utsavsync-session')
    return null
  }
}

function App() {
  const [loginSession, setLoginSession] = useState(readRememberedSession)
  const [role, setRole] = useState(() => loginSession?.user?.app_metadata?.role === 'volunteer' ? 'Volunteer' : loginSession ? 'Visitor' : '')
  const [email, setEmail] = useState(() => loginSession?.user?.email || '')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(() => Boolean(loginSession))
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState('')
  const [page, setPage] = useState(() => loginSession ? 2 : 1)
  const [language, setLanguage] = useState(savedLanguage)
  const [gateOpen, setGateOpen] = useState(false)
  const [volunteerCode, setVolunteerCode] = useState('')
  const [volunteerToken, setVolunteerToken] = useState(() => loginSession?.access_token?.startsWith('vs1.') ? loginSession.access_token : '')
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState('signin')
  const isSignup = mode === 'signup'

  /* Supabase logins last about an hour: renew a minute before expiry (or right away
     if a remembered one already expired); if that fails, go back to sign-in. */
  useEffect(() => {
    if (!loginSession?.refresh_token) return undefined
    const wait = Math.max(0, (loginSession.expires_at - 60) * 1000 - Date.now())
    const timer = setTimeout(async () => {
      try {
        const next = await refreshSession(loginSession.refresh_token)
        setLoginSession(next)
        if (window.localStorage.getItem('utsavsync-session')) window.localStorage.setItem('utsavsync-session', JSON.stringify(next))
      } catch {
        setLoginSession(null)
        setVolunteerToken('')
        setPage(1)
        window.localStorage.removeItem('utsavsync-session')
        setMessage('Your session expired. Please sign in again.')
      }
    }, wait)
    return () => clearTimeout(timer)
  }, [loginSession])
  function changeLanguage(nextLanguage) {
    setLanguage(nextLanguage)
    window.localStorage.setItem('utsavsync-language', nextLanguage)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!role) {
      setMessage('Choose Visitor or Volunteer to continue.')
      return
    }
    if (!authConfigured) {
      setMessage(NOT_CONFIGURED)
      return
    }
    setBusy(true)
    setMessage('')
    try {
      const session = isSignup ? await signUp(email, password) : await signInWithPassword(email, password)
      if (!session) {
        setMode('signin')
        setPassword('')
        setMessage('Account created. Open the confirmation link sent to ' + email + ', then sign in.')
        return
      }
      setLoginSession(session)
      let chosenRole = role
      if (session?.user?.app_metadata?.role === 'volunteer') chosenRole = 'Volunteer'
      setRole(chosenRole)
      if (remember && session) window.localStorage.setItem('utsavsync-session', JSON.stringify(session))
      else window.localStorage.removeItem('utsavsync-session')
      if (chosenRole === 'Volunteer' && !volunteerToken && session?.user?.app_metadata?.role !== 'volunteer') {
        setGateOpen(true)
        return
      }
      setPage(2)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function verifyVolunteerCode(event) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    try {
      const verified = await api('/volunteers/verify-code', {
        method: 'POST',
        body: { email, access_code: volunteerCode },
      })
      setVolunteerToken(verified.access_token)
      setRole('Volunteer')
      const session = {
        access_token: verified.access_token,
        expires_at: verified.expires_at,
        user: { id: verified.user_id, email, app_metadata: { role: 'volunteer' } },
      }
      setLoginSession(session)
      if (remember) window.localStorage.setItem('utsavsync-session', JSON.stringify(session))
      setGateOpen(false)
      setPage(2)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  async function forgotPassword() {
    if (!email) {
      setMessage('Enter your email first, then choose Forgot password.')
      return
    }
    try {
      await requestPasswordRecovery(email)
      setMessage('Password recovery email sent. Check your inbox.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  if (page === 2) {
    const userEmail = loginSession?.user?.email || email
    const userRole = role.toLowerCase()
    const session = volunteerToken
      ? { ...loginSession, access_token: volunteerToken, user: { ...loginSession?.user, id: 'volunteer:' + userEmail.toLowerCase(), email: userEmail, app_metadata: { role: 'volunteer' } } }
      : loginSession
    return <VisitorDashboard onBackToLogin={() => { signOutRemote(loginSession?.access_token); setPage(1); setLoginSession(null); setVolunteerToken(''); setRole(''); setPassword(''); setRemember(false); window.localStorage.removeItem('utsavsync-session') }} userEmail={userEmail} userRole={userRole} session={session} language={language} onLanguageChange={changeLanguage} />
  }

  return (
    <LocalizedText language={language}>
      <main className="login-page">
        <div className="login-art" aria-hidden="true" />
        <label className="language-picker"><span>Language</span><select value={language} onChange={event => changeLanguage(event.target.value)} aria-label="Change language">{languageOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        <section className="login-card" aria-label="UtsavSync sign in">
          <header className="brand-block">
            <h1 className="brand-name"><span>Utsav</span><span>Sync</span></h1>
            <p className="brand-tagline">Smart Festival Operations</p>
            <div className="ornament-rule" aria-hidden="true" />
            <h2>{isSignup ? 'Join UtsavSync' : 'Welcome back'}</h2>
            <p className="welcome-copy">{isSignup ? 'Create your account to keep Mumbai’s festivals safe and clean.' : 'Sign in to help keep Mumbai’s festivals safe and clean.'}</p>
          </header>

          <div className="role-choices" role="group" aria-label="Choose your role">
            <button type="button" className={'role-choice visitor-choice ' + (role === 'Visitor' ? 'selected' : '')} aria-pressed={role === 'Visitor'} onClick={() => { setRole('Visitor'); setMessage('') }}>
              <strong>Visitor</strong><span>Join &amp; Explore</span>
            </button>
            <button type="button" className={'role-choice volunteer-choice ' + (role === 'Volunteer' ? 'selected' : '')} aria-pressed={role === 'Volunteer'} onClick={() => { setRole('Volunteer'); setMessage('') }}>
              <strong>Volunteer</strong><span>Report &amp; Support</span>
            </button>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="field-label email-label" htmlFor="email">Email address</label>
            <div className="field-wrap email-wrap"><input id="email" type="email" placeholder="you@example.com" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required /></div>
            <label className="field-label password-label" htmlFor="password">Password</label>
            <div className="field-wrap password-wrap"><input id="password" type={showPassword ? 'text' : 'password'} placeholder={isSignup ? 'Create a password (6+ characters)' : 'Enter your password'} autoComplete={isSignup ? 'new-password' : 'current-password'} minLength={6} value={password} onChange={event => setPassword(event.target.value)} required /><button type="button" className={'password-toggle ' + (showPassword ? 'password-visible' : 'password-hidden')} aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(value => !value)} /></div>
            <div className="login-options">
              <label className="remember-option"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} /><span>Remember me</span></label>
              {!isSignup && <button type="button" className="forgot-link" onClick={forgotPassword}>Forgot password?</button>}
            </div>
            <button className="signin-button" type="submit" aria-label={isSignup ? 'Create account' : 'Sign in'} disabled={busy}><span>{busy ? 'Checking…' : isSignup ? 'Create account' : 'Sign in'}</span></button>
          </form>
          <p className="auth-switch">
            <span>{isSignup ? 'Already have an account?' : 'New to UtsavSync?'}</span>
            <button type="button" className="forgot-link" onClick={() => { setMode(isSignup ? 'signin' : 'signup'); setMessage('') }}>{isSignup ? 'Sign in' : 'Create account'}</button>
          </p>
        </section>

        {gateOpen && <div className="volunteer-gate-backdrop">
          <section className="volunteer-gate" role="dialog" aria-modal="true" aria-labelledby="volunteer-gate-title">
            <button type="button" className="gate-close" onClick={() => setGateOpen(false)} aria-label="Cancel">×</button>
            <span className="gate-emblem" aria-hidden="true">✺</span>
            <p className="eyebrow">VOLUNTEER VERIFICATION</p>
            <h2 id="volunteer-gate-title">Volunteer access code</h2>
            <p>Enter the one-time code from your festival coordinator.</p>
            <form onSubmit={verifyVolunteerCode}>
              <label htmlFor="volunteer-code">Volunteer access code</label>
              <input id="volunteer-code" type="password" autoComplete="one-time-code" value={volunteerCode} onChange={event => setVolunteerCode(event.target.value)} required minLength={12} />
              <button className="gate-submit" type="submit" disabled={busy}>{busy ? 'Checking code…' : 'Verify code & continue'}</button>
              <button className="gate-cancel" type="button" onClick={() => setGateOpen(false)}>Cancel</button>
            </form>
          </section>
        </div>}
        {message && <p className="login-message" role="status">{message}</p>}
      </main>
    </LocalizedText>
  )
}

export default App

