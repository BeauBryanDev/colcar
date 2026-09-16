/**
 * The dashboard chrome: brand bar, nav tabs, signed-in account, logout.
 */

import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import {
  FiCalendar,
  FiFileText,
  FiGrid,
  FiLogOut,
  FiStar,
  FiUser,
  FiUsers,
} from 'react-icons/fi'
import mainIconUrl from '@/assets/main_icon.svg'
import colombiaIconUrl from '@/assets/colombia.svg'
import { useAuth } from '@/stores/authContext'

const ROLE_LABEL: Record<string, string> = {
  admin: 'Administrador',
  staff: 'Personal',
  user: 'Usuario',
}

export const AdminShell: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/admin/login', { replace: true })
  }

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    [
      'flex items-center gap-2 px-4 py-2.5 font-display text-base tracking-wider uppercase',
      'border-b-4 transition-colors',
      isActive
        ? 'border-brand-yellow text-brand-yellow'
        : 'border-transparent text-white/60 hover:text-white hover:border-white/30',
    ].join(' ')

  return (
    <div className="min-h-screen bg-brand-red/20 flex flex-col">
      <header className="bg-brand-navy border-b-4 border-brand-red">
        <div className="px-6 lg:px-10 py-2.5 flex items-center gap-4">
          {/* Back to the customer flow, same as the customer header. */}
          <Link
            to="/"
            aria-label="Ir al inicio"
            className="flex-shrink-0 rounded-lg hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-brand-yellow/60 transition-opacity"
          >
            <img
              src={mainIconUrl}
              alt=""
              className="w-10 h-10 object-contain"
              aria-hidden="true"
            />
          </Link>
          <span className="font-display text-white text-2xl tracking-widest uppercase leading-none">
            CAR-INSPECTOR
          </span>
          <FiStar
            className="w-7 h-7 text-brand-yellow fill-brand-yellow flex-shrink-0"
            aria-hidden="true"
          />
          <span className="h-7 w-px bg-white/30" aria-hidden="true" />
          <span className="font-display text-brand-yellow text-base tracking-wider uppercase">
            Panel Administrativo
          </span>

          <div className="flex-1" />

          <img
            src={colombiaIconUrl}
            alt="Colombia"
            className="hidden md:block w-8 h-8 object-contain"
          />

          <div className="flex items-center gap-2 bg-white/10 rounded-xl px-3 py-1.5 border border-white/20">
            <div className="w-8 h-8 rounded-full bg-brand-blue flex items-center justify-center flex-shrink-0">
              <FiUser className="w-5 h-5 text-white" />
            </div>
            <div className="hidden sm:flex flex-col leading-tight">
              <span className="text-white font-semibold text-xs">
                {user?.fullName || user?.username}
              </span>
              <span className="text-brand-yellow text-[10px] uppercase tracking-wide">
                {ROLE_LABEL[user?.role ?? ''] ?? user?.role}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-2 text-white/70 hover:text-brand-red transition-colors px-2 py-2"
            aria-label="Cerrar sesión"
          >
            <FiLogOut className="w-5 h-5" />
            <span className="hidden lg:inline text-sm font-semibold">
              Salir
            </span>
          </button>
        </div>

        <nav className="px-6 lg:px-10 flex items-end gap-1 overflow-x-auto">
          <NavLink to="/admin/appointments" className={tabClass}>
            <FiCalendar className="w-5 h-5" />
            Citas
          </NavLink>
          <NavLink to="/admin/calendar" className={tabClass}>
            <FiGrid className="w-5 h-5" />
            Calendario
          </NavLink>
          <NavLink to="/admin/inspections" className={tabClass}>
            <FiFileText className="w-5 h-5" />
            Inspecciones
          </NavLink>
          {/* Hidden for staff: the backend answers 403, and a tab that always
              fails is worse than no tab. */}
          {isAdmin && (
            <NavLink to="/admin/users" className={tabClass}>
              <FiUsers className="w-5 h-5" />
              Usuarios
            </NavLink>
          )}
        </nav>
      </header>

      <main className="flex-1 p-4 lg:p-6">{children}</main>

      <footer className="bg-brand-blue text-white/70 text-xs px-6 py-2.5 flex items-center justify-between">
        <span className="uppercase tracking-wider">
          Beau Auto-Repairs · Panel Administrativo
        </span>
        <span className="uppercase tracking-wider">
          RTM · NTC 5375 · Resolución 3768 de 2013
        </span>
      </footer>
    </div>
  )
}

export default AdminShell
