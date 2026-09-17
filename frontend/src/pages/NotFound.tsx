
import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FiAlertTriangle, FiArrowLeft, FiHome, FiLock, FiRefreshCw, FiSearch } from 'react-icons/fi'
import mainIconUrl from '@/assets/main_icon.svg'
import colombiaIconUrl from '@/assets/colombia.svg'
import { Button } from '@/components/common/Button'

export type ErrorCode = 403 | 404 | 500


/**
 * The error page, for every HTTP-shaped failure the SPA can show a human.
 */

interface Copy {
  code: string
  title: string
  message: string
  icon: React.ReactNode
  /** Tailwind text colour for the code and icon. */
  tone: string
}

const COPY: Record<ErrorCode, Copy> = {
  403: {
    code: '403',
    title: 'Acceso restringido',
    message:
      'Tu cuenta no tiene permisos para esta sección. Si crees que deberías tenerlos, pídelo a un administrador.',
    icon: <FiLock className="w-10 h-10" />,
    tone: 'text-brand-yellow',
  },
  404: {
    code: '404',
    title: 'Página no encontrada',
    message:
      'La dirección no existe o cambió de lugar. Revisa el enlace o vuelve al inicio.',
    icon: <FiSearch className="w-10 h-10" />,
    tone: 'text-brand-yellow',
  },
  500: {
    code: '500',
    title: 'Error del servidor',
    message:
      'Algo falló de nuestro lado. Vuelve a intentarlo en un momento; si persiste, comunícate con Beau Auto-Repairs.',
    icon: <FiAlertTriangle className="w-10 h-10" />,
    tone: 'text-brand-red',
  },
}

interface ErrorPageProps {
  code?: ErrorCode
  /** Overrides the canned message — e.g. which role a 403 actually needed. */
  detail?: string
}

export const ErrorPage: React.FC<ErrorPageProps> = ({ code = 404, detail }) => {
  const copy = COPY[code]
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-brand-navy flex flex-col">
      {/* Same brand bar as the login page; the icon goes home. */}
      <header className="border-b-4 border-brand-red">
        <div className="px-6 lg:px-10 py-3 flex items-center gap-3">
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
          <span className="font-display text-white text-2xl tracking-widest uppercase">
            CAR-INSPECTOR
          </span>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-lg text-center">
          <div
            className={`inline-flex items-center justify-center w-20 h-20 rounded-full bg-white/5 border-2 border-white/10 mb-5 ${copy.tone}`}
          >
            {copy.icon}
          </div>

          <p
            className={`font-display text-6xl tracking-widest leading-none ${copy.tone}`}
          >
            {copy.code}
          </p>
          <h1 className="font-display text-3xl text-white tracking-wider uppercase mt-2">
            {copy.title}
          </h1>
          <p className="text-white/60 text-sm mt-3 max-w-md mx-auto">
            {detail ?? copy.message}
          </p>

          <div className="flex flex-wrap items-center justify-center gap-2 mt-7">
            {code === 500 ? (
              <Button
                variant="yellow"
                size="lg"
                icon={<FiRefreshCw className="w-4 h-4" />}
                onClick={() => window.location.reload()}
              >
                Reintentar
              </Button>
            ) : (
              <Button
                variant="yellow"
                size="lg"
                icon={<FiHome className="w-4 h-4" />}
                onClick={() => navigate('/')}
              >
                Ir al inicio
              </Button>
            )}
            <Button
              variant="ghost"
              size="lg"
              icon={<FiArrowLeft className="w-4 h-4" />}
              onClick={() => navigate(-1)}
            >
              Volver
            </Button>
          </div>

          {/* Logging in again as the same account does not fix a 403 — the way
              out is a different account, or the part of the panel they can use. */}
          {code === 403 && (
            <p className="text-white/50 text-sm mt-5">
              <Link to="/admin" className="text-brand-yellow hover:underline">
                Ir al panel
              </Link>
              {' · '}
              <Link
                to="/admin/login"
                className="text-brand-red hover:text-red-400 hover:underline"
              >
                Entrar con otra cuenta
              </Link>
            </p>
          )}

          <div className="flex items-center justify-center gap-2 mt-8">
            <img
              src={colombiaIconUrl}
              alt="Colombia"
              className="w-6 h-6 object-contain"
            />
            <span className="text-white/40 text-xs uppercase tracking-wider">
              Beau Auto-Repairs · RTM Compliance
            </span>
          </div>
        </div>
      </main>
    </div>
  )
}

/**
 * Catches render crashes anywhere below it and shows the 500 page instead of
 * React's blank screen.
 *
 * A class, because `componentDidCatch` has no hook equivalent — this is the one
 * place React still requires one. It deliberately does NOT catch failed API
 * calls: those are handled where they happen (`ErrorState` inside each page),
 * so one dead endpoint does not blank the whole dashboard.
 */
export class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { crashed: boolean }
> {
  state = { crashed: false }

  static getDerivedStateFromError() {
    return { crashed: true }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // The console is the only sink we have; there is no client telemetry.
    console.error('Render crash:', error, info.componentStack)
  }

  render() {
    return this.state.crashed ? <ErrorPage code={500} /> : this.props.children
  }
}

/** Default: the catch-all route. */
export const NotFound: React.FC = () => <ErrorPage code={404} />

export default NotFound
