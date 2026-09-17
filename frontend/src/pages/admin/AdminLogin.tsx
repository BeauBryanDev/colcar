/**
 * Admin login. Separate route from the customer flow, which never sends a token.
 *
 * The 401 body is deliberately the same for a wrong password, an unknown user
 * and a disabled account — the backend refuses to be a user-enumeration oracle
 * — so this page shows whatever it is told and never guesses at a friendlier
 * "no such user".
 */

import React, { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { FiAlertCircle, FiLock, FiStar, FiUser } from 'react-icons/fi'
import mainIconUrl from '@/assets/main_icon.svg'
import colombiaIconUrl from '@/assets/colombia.svg'
import { Button } from '@/components/common/Button'
import { useAuth } from '@/stores/authContext'

interface LocationState {
  from?: { pathname?: string }
  /** Which entry in the customer header was clicked. A label, never a claim. */
  intent?: 'admin' | 'staff'
}

/**
 * Only ever rendered as a subtitle. **The role comes from the account**, not
 * from the link that got here — one login endpoint, and the backend decides
 * what the credentials are worth.
 */
const INTENT_LABEL: Record<string, string> = {
  admin: 'Acceso de administrador',
  staff: 'Acceso de personal',
}

export const AdminLogin: React.FC = () => {
  const { login, user, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const state = location.state as LocationState | null
  // Where RequireAuth was trying to send them before the redirect.
  const from = state?.from?.pathname ?? '/admin'
  const intent = state?.intent ? INTENT_LABEL[state.intent] : null

  // Already signed in (or just signed in): leave the login page.
  useEffect(() => {
    if (!loading && user) navigate(from, { replace: true })
  }, [user, loading, from, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return

    setSubmitting(true)
    setError(null)
    try {
      await login(username.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'No se pudo iniciar sesión.',
      )
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-navy flex flex-col">
      {/* Brand bar — the same navy / red rule as the customer header */}
      <header className="border-b-4 border-brand-red">
        <div className="px-6 lg:px-10 py-3 flex items-center gap-3">
          <img
            src={mainIconUrl}
            alt=""
            className="w-10 h-10 object-contain"
            aria-hidden="true"
          />
          <span className="font-display text-white text-2xl tracking-widest uppercase">
            CAR-INSPECTOR
          </span>
          <FiStar
            className="w-7 h-7 text-brand-yellow fill-brand-yellow"
            aria-hidden="true"
          />
          <span className="h-7 w-px bg-white/30 mx-1" aria-hidden="true" />
          <span className="font-display text-brand-yellow text-base tracking-wider uppercase">
            Panel administrativo
          </span>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <form
            onSubmit={handleSubmit}
            className="bg-white/5 border-2 border-white/10 rounded-2xl p-8 shadow-2xl"
          >
            <div className="flex flex-col items-center mb-6">
              <div className="w-16 h-16 rounded-full bg-brand-blue flex items-center justify-center mb-3">
                <FiLock className="w-8 h-8 text-brand-yellow" />
              </div>
              <h1 className="font-display text-3xl text-white tracking-wider uppercase">
                Iniciar sesión
              </h1>
              <p className="text-white/50 text-sm mt-1">
                {intent ?? 'Beau Auto-Repairs · acceso restringido'}
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 bg-brand-red/20 border border-brand-red/60 rounded-lg px-3 py-2.5 mb-4"
              >
                <FiAlertCircle className="w-5 h-5 text-brand-red flex-shrink-0 mt-0.5" />
                <span className="text-white text-sm">{error}</span>
              </div>
            )}

            <label className="block mb-4">
              <span className="text-white/70 text-xs uppercase tracking-wide font-semibold">
                Usuario
              </span>
              <div className="mt-1 relative">
                <FiUser className="w-5 h-5 text-white/40 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-brand-navy border-2 border-white/20 focus:border-brand-yellow rounded-lg pl-10 pr-3 py-2.5 text-white placeholder-white/30 outline-none transition-colors"
                  placeholder="usuario"
                />
              </div>
            </label>

            <label className="block mb-6">
              <span className="text-white/70 text-xs uppercase tracking-wide font-semibold">
                Contraseña
              </span>
              <div className="mt-1 relative">
                <FiLock className="w-5 h-5 text-white/40 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-brand-navy border-2 border-white/20 focus:border-brand-yellow rounded-lg pl-10 pr-3 py-2.5 text-white placeholder-white/30 outline-none transition-colors"
                  placeholder="••••••••"
                />
              </div>
            </label>

            <Button
              type="submit"
              variant="yellow"
              size="lg"
              fullWidth
              loading={submitting}
              disabled={!username.trim() || !password}
            >
              Entrar
            </Button>

            {/* Way out of the restricted area, back to the customer flow. */}
            <div className="text-center mt-4">
              <Link
                to="/"
                className="text-brand-red hover:text-red-400 hover:underline text-sm font-semibold transition-colors"
              >
                Regresar al inicio
              </Link>
            </div>
          </form>

          <div className="flex items-center justify-center gap-2 mt-6">
            <img
              src={colombiaIconUrl}
              alt="Colombia"
              className="w-6 h-6 object-contain"
            />
            <span className="text-white/40 text-xs uppercase tracking-wider">
              RTM Compliance · Colombia
            </span>
          </div>
        </div>
      </main>
    </div>
  )
}

export default AdminLogin
