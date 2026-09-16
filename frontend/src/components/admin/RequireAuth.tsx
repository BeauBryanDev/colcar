/**
 * Route guard. Mirrors `require_role` on the backend — ranked, not equality,
 * so an admin passes a `staff` gate.
 *
 * This is **convenience, not security**: it decides what to render, and anyone
 * can edit their own localStorage. Every protected read still goes through the
 * backend's own guard, which is what actually says no.
 */

import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ErrorPage } from '@/pages/NotFound'
import { useAuth } from '@/stores/authContext'
import type { UserRole } from '@/types/admin'

interface RequireAuthProps {
  children: React.ReactNode
  /** Minimum role. Omit for "any authenticated account". */
  minimum?: UserRole
}

export const RequireAuth: React.FC<RequireAuthProps> = ({
  children,
  minimum,
}) => {
  const { user, loading, hasRole } = useAuth()
  const location = useLocation()

  // Wait for /auth/me. Redirecting here would bounce a valid session to the
  // login page on every refresh.
  if (loading) {
    return (
      <div className="min-h-screen bg-brand-navy flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <span className="w-10 h-10 border-4 border-brand-yellow border-t-transparent rounded-full animate-spin" />
          <span className="text-white/60 text-sm">Verificando sesión…</span>
        </div>
      </div>
    )
  }

  if (!user) {
    // `state.from` so the login page can return the user where they were going.
    return <Navigate to="/admin/login" replace state={{ from: location }} />
  }

  if (minimum && !hasRole(minimum)) {
    // The shared 403 page, told exactly which role was missing — the same
    // situation the backend answers 403 for.
    return (
      <ErrorPage
        code={403}
        detail={`Esta sección requiere el rol "${minimum}". Tu cuenta tiene el rol "${user.role}".`}
      />
    )
  }

  return <>{children}</>
}

export default RequireAuth
