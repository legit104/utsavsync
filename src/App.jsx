
import { useState } from 'react'
import './App.css'

function App() {
  const [role, setRole] = useState('Visitor')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [message, setMessage] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    setMessage(
      `UI ready for ${role}. Authentication will be connected next.`
    )
  }

  return (
    <main className="login-page">
      <div className="login-art" aria-hidden="true" />

      <button
        type="button"
        className={`hotspot visitor-hotspot ${role === 'Visitor' ? 'selected' : ''}`}
        aria-label="Choose Visitor"
        onClick={() => {
          setRole('Visitor')
          setMessage('')
        }}
      />

      <button
        type="button"
        className={`hotspot volunteer-hotspot ${role === 'Volunteer' ? 'selected' : ''}`}
        aria-label="Choose Volunteer"
        onClick={() => {
          setRole('Volunteer')
          setMessage('')
        }}
      />

      <form className="login-form" onSubmit={handleSubmit}>
        <input
          className="email-input"
          type="email"
          aria-label="Email address"
          placeholder="you@example.com"
          autoComplete="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          required
        />

        <input
          className="password-input"
          type="password"
          aria-label="Password"
          placeholder="Enter your password"
          autoComplete="current-password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
        />

        <input
          className="remember-input"
          type="checkbox"
          aria-label="Remember me"
          checked={remember}
          onChange={e => setRemember(e.target.checked)}
        />

        <button
          className="hotspot forgot-hotspot"
          type="button"
          aria-label="Forgot password"
          onClick={() => setMessage('Password recovery will be connected next.')}
        />

        <button
          className="hotspot signin-hotspot"
          type="submit"
          aria-label="Sign in"
        />

        <button
          className="hotspot signup-hotspot"
          type="button"
          aria-label="Create account"
          onClick={() => setMessage('Account creation will be connected next.')}
        />

        {message && (
          <p className="login-message" role="status">
            {message}
          </p>
        )}
      </form>
    </main>
  )
}

export default App
