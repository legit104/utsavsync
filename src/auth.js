const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || '').replace(/\/$/, '')
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const authConfigured = Boolean(supabaseUrl && anonKey)
export const NOT_CONFIGURED = 'Accounts are not set up on this computer. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to the frontend .env, then restart npm run dev.'

/* Supabase's error messages, in words a festival visitor understands. */
const FRIENDLY_ERRORS = [
  [/invalid login credentials/i, 'Wrong email or password. If you are new, create an account first.'],
  [/email not confirmed/i, 'Please confirm your email first: open the link sent to your inbox, then sign in.'],
  [/user already registered/i, 'An account with this email already exists. Sign in instead.'],
  [/rate limit/i, 'Too many attempts right now. Please wait a few minutes and try again.'],
]

async function authRequest(path, payload, fallback) {
  if (!authConfigured) throw new Error(NOT_CONFIGURED)
  const response = await fetch(supabaseUrl + '/auth/v1/' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', apikey: anonKey },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const raw = data.msg || data.message || data.error_description || fallback
    throw new Error(FRIENDLY_ERRORS.find(([pattern]) => pattern.test(raw))?.[1] || raw)
  }
  return data
}

function withExpiry(data) {
  return { ...data, expires_at: data.expires_at || Math.floor(Date.now() / 1000) + (data.expires_in || 3600) }
}

export async function signInWithPassword(email, password) {
  return withExpiry(await authRequest('token?grant_type=password', { email, password }, 'Email or password was not accepted.'))
}

/* Returns a session when the account can sign in straight away, or null when
   Supabase first sends a confirmation email. */
export async function signUp(email, password) {
  const data = await authRequest('signup', { email, password }, 'Could not create the account.')
  return data.access_token ? withExpiry(data) : null
}

export async function refreshSession(refreshToken) {
  return withExpiry(await authRequest('token?grant_type=refresh_token', { refresh_token: refreshToken }, 'Session expired.'))
}

export function signOutRemote(accessToken) {
  if (!authConfigured || !accessToken || accessToken.startsWith('vs1.')) return
  fetch(supabaseUrl + '/auth/v1/logout', {
    method: 'POST', headers: { apikey: anonKey, Authorization: 'Bearer ' + accessToken },
  }).catch(() => {})
}

export async function requestPasswordRecovery(email) {
  if (!authConfigured) throw new Error('Password recovery is available after Supabase is configured.')
  await authRequest('recover', { email }, 'Could not send the recovery email.')
}
