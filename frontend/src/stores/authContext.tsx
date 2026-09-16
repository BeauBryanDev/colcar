/**
 * Who is logged in, for the whole admin area.
 *
 * A React context rather than a Zustand store because this is read-mostly and
 * the customer flow's `inspectionStore` has no business knowing about it — the
 * two areas share nothing but the axios client.
 *
 * **The backend is the authority.** On mount, a stored token is validated with
 * `GET /auth/me`; a 401 clears the session. The cached user is painted first so
 * the shell does not flash, but it is never treated as proof — the account may
 * have been disabled since the token was issued, and the backend re-reads
 * `active` on every request precisely so that takes effect immediately.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { authService } from '@/services/authService'
import type { AdminUser, UserRole } from '@/types/admin'

interface AuthContextValue {
  user: AdminUser | null
  /** True until the initial `/auth/me` check settles — render a spinner, not a redirect. */
  loading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  /** Ranked, like the backend's guard: an admin satisfies `hasRole('staff')`. */
  hasRole: (minimum: UserRole) => boolean
  isAdmin: boolean
}

const RANK: Record<UserRole, number> = { user: 0, staff: 1, admin: 2 }

const AuthContext = createContext<AuthContextValue | null>(null)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  // Painted immediately from cache; replaced (or cleared) by /auth/me below.
  const [user, setUser] = useState<AdminUser | null>(() =>
    authService.getToken() ? authService.getCachedUser() : null,
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const validate = async () => {
      const token = authService.getToken()
      // No token, or one whose `exp` has already passed: skip a doomed call.
      if (!token || authService.isExpired()) {
        authService.clearSession()
        if (!cancelled) {
          setUser(null)
          setLoading(false)
        }
        return
      }
      try {
        const fresh = await authService.me()
        if (!cancelled) setUser(fresh)
      } catch {
        // Expired, revoked, deleted or deactivated — all the same here.
        authService.clearSession()
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void validate()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setError(null)
    try {
      const data = await authService.login({ username, password })
      setUser(data.user)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'No se pudo iniciar sesión.'
      setError(message)
      throw err
    }
  }, [])

  const logout = useCallback(() => {
    authService.clearSession()
    setUser(null)
    setError(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      error,
      login,
      logout,
      hasRole: (minimum) => (user ? RANK[user.role] >= RANK[minimum] : false),
      isAdmin: user?.role === 'admin',
    }),
    [user, loading, error, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an <AuthProvider>')
  return ctx
}

export default AuthProvider
