import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FiStar, FiChevronDown, FiUser, FiShield, FiUsers } from 'react-icons/fi'
import claudeLogoUrl from '@/assets/claude-logo.png'
import mainIconUrl from '@/assets/main_icon.svg'
import colombiaIconUrl from '@/assets/colombia.svg'
import carIconUrl from '@/assets/car_icon.svg'
import vanIconUrl from '@/assets/van.svg'
import CarDoor from '@/assets/CarDoor.svg'

// Backend Icons
import PythonIcon from '@/assets/Python.svg'
import FastAPIIcon from '@/assets/FastAPI.svg'
import OpenCVIcon from '@/assets/OpenCV.svg'
import NumpyIcon from '@/assets/Numpy.svg'
import YOLOIcon from '@/assets/Ultralytics.webp'
import MongoDBIcon from '@/assets/MongoDB.svg'
import AnthropicIcon from '@/assets/Anthropic.webp'

// Frontend Icons
import ReactIcon from '@/assets/React.svg'
import TypeScriptIcon from '@/assets/TypeScript.svg'
import TailwindIcon from '@/assets/Tailwindcss.svg'
import ViteIcon from '@/assets/Vite.svg'

type Credit = { src: string; label: string; link: string }

const BACKEND_CREDITS: Credit[] = [
  { src: PythonIcon, label: 'Python', link: 'https://www.python.org/' },
  { src: FastAPIIcon, label: 'FastAPI', link: 'https://fastapi.tiangolo.com/' },
  { src: OpenCVIcon, label: 'OpenCV', link: 'https://opencv.org/' },
  { src: NumpyIcon, label: 'Numpy', link: 'https://numpy.org/' },
  { src: YOLOIcon, label: 'YOLO', link: 'https://ultralytics.com/' },
  { src: MongoDBIcon, label: 'MongoDB', link: 'https://www.mongodb.com/' },
  { src: AnthropicIcon, label: 'Anthropic', link: 'https://www.anthropic.com/' },
]

const FRONTEND_CREDITS: Credit[] = [
  { src: TypeScriptIcon, label: 'TypeScript', link: 'https://www.typescriptlang.org/' },
  { src: ReactIcon, label: 'React', link: 'https://reactjs.org/' },
  { src: TailwindIcon, label: 'Tailwind', link: 'https://tailwindcss.com/' },
  { src: ViteIcon, label: 'Vite', link: 'https://vitejs.dev/' },
]

export const Header: React.FC = () => {
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const navigate = useNavigate()

  /**
   * "Usuarios" points at `/admin/users`, which is admin-only: `RequireAuth`
   * bounces an anonymous visitor to the login page and returns them there
   * afterwards.
   */
  const menuItems = [
    {
      label: 'Ingresar como Administrador',
      icon: <FiShield className="w-4 h-4" />,
      go: () => navigate('/admin/login', { state: { intent: 'admin' } }),
    },
    {
      label: 'Ingresar como Personal',
      icon: <FiUser className="w-4 h-4" />,
      go: () => navigate('/admin/login', { state: { intent: 'staff' } }),
    },
    {
      label: 'Usuarios',
      icon: <FiUsers className="w-4 h-4" />,
      go: () => navigate('/admin/users'),
    },
  ]

  return (
    <header className="bg-brand-navy border-b-4 border-brand-red w-full">
      {/* py-[15px] rather than py-2.5 (10px): +5px top and bottom is the
          +10px of header height. */}
      <div className="w-full px-6 lg:px-10 py-[15px] flex items-center gap-4">

        {/* BRAND */}
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* The icon is the way back to the start of the flow. The <img>
              stays aria-hidden and the label lives on the link, so a screen
              reader announces one control rather than an unnamed image. */}
          <Link
            to="/"
            aria-label="Ir al inicio"
            className="flex-shrink-0 rounded-lg hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-brand-yellow/60 transition-opacity"
          >
            <img src={mainIconUrl} alt="" className="w-12 h-12 flex-shrink-0 object-contain" aria-hidden="true" />
          </Link>
          <div className="flex flex-col leading-none">
            <span className="font-display text-white text-3xl tracking-widest uppercase leading-none">
              CAR-INSPECTOR 
            </span>
            <p className="text-brand-yellow text-base tracking-wider uppercase">Beau-Auto-Repairs</p>
          </div>
          <FiStar className="w-9 h-9 text-brand-yellow fill-brand-yellow" aria-hidden="true" />
          {/* Vertical divider */}
          <span className="h-8 w-px bg-white/30 mx-1" aria-hidden="true" />
          <div className="flex flex-col leading-tight">
            <span className="font-display text-brand-yellow text-base tracking-wider uppercase">
              AGENTE DE AUTODIAGNÓSTICO
            </span>
            <span className="font-display text-brand-yellow text-base tracking-wider uppercase">
              DE VEHÍCULOS INTELIGENTE
            </span>
          </div>
           <img src={carIconUrl} alt="" className="w-16 h-16 flex-shrink-0 object-contain" aria-hidden="true" />
        </div>

        {/* Spacer — carries the backend rail, which is hidden below xl, so on a
            narrow screen this is a plain spacer again. */}
        <div className="flex-1 flex items-center justify-center">
          <CreditRail credits={BACKEND_CREDITS} />
        </div>

        {/* RTM COMPLIANCE */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <img src={CarDoor} alt="" className="w-10 h-10 flex-shrink-0 object-contain" aria-hidden="true" />
          <img src={colombiaIconUrl} alt="Colombia" className="w-10 h-10 flex-shrink-0 object-contain" />
          <img src={vanIconUrl} alt="" className="w-10 h-10 flex-shrink-0 object-contain" aria-hidden="true" />
          <span className="font-display text-white text-lg tracking-wider uppercase">
            RTM COMPLIANCE
          </span>
        </div>

        {/* Spacer — frontend rail, same hidden-below-xl rule. */}
        <div className="flex-1 flex items-center justify-center">
          <CreditRail credits={FRONTEND_CREDITS} />
        </div>
        <img src={carIconUrl} alt="" className="w-16 h-16 flex-shrink-0 object-contain" aria-hidden="true" />
        {/*CLAUDE BADGE */}
        <div className="hidden sm:flex items-center gap-2 bg-white/10 rounded-xl px-3 py-2 border border-white/20">
        
          <img src={claudeLogoUrl} alt="Claude" className="w-10 h-10 flex-shrink-0 object-contain" />
          <div className="flex flex-col leading-tight">
            <span className="text-white/60 text-[10px] uppercase tracking-wide">
              Powered by
            </span>
            <span className="text-white font-bold text-sm">Claude</span>
          </div>
        </div>

        {/*  USER PROFILE */}
        <div className="relative">
          <button
            type="button"
            aria-label="Menú de usuario"
            aria-expanded={userMenuOpen}
            onClick={() => setUserMenuOpen((v) => !v)}
            className="flex items-center gap-2 bg-white/10 hover:bg-white/20 rounded-xl px-3 py-2 border border-white/20 transition-colors"
          >
            <div className="w-10 h-10 rounded-full bg-brand-blue flex items-center justify-center flex-shrink-0">
              <FiUser className="w-6 h-6 text-white" />
            </div>
            <FiChevronDown
              className={`w-5 h-5 text-white/60 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {/* Dropdown */}
          {userMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-full mt-1 w-56 bg-brand-navy border border-white/20 rounded-xl shadow-xl z-50 py-1"
            >
              {menuItems.map((item) => (
                <button
                  key={item.label}
                  role="menuitem"
                  className="w-full flex items-center gap-2.5 text-left px-4 py-2.5 text-sm text-white/80 hover:bg-white/10 hover:text-white transition-colors"
                  onClick={() => {
                    setUserMenuOpen(false)
                    item.go()
                  }}
                >
                  <span className="text-brand-yellow flex-shrink-0">
                    {item.icon}
                  </span>
                  {item.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

/**
 * One rail of the credit strip: thanks to these projects. The two rails sit in
 * the spacers flanking RTM COMPLIANCE; the LLM attribution is the Claude badge
 * on the right of the bar.
 */
function CreditRail({ credits }: { credits: Credit[] }) {
  return (
    <span className="hidden xl:flex items-center gap-6 2xl:gap-8">
      {credits.map(({ src, label, link }) => (
        <a
          key={label}
          href={link}
          target="_blank"
          // noopener is the security half (the opened tab cannot reach back through
          // window.opener); noreferrer keeps it working in older browsers too.
          rel="noopener noreferrer"
          title={label}
          aria-label={label}
          className="opacity-75 transition hover:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#D6D6D6]"
        >
          <img
            src={src}
            alt={label}
            // 40px matches the other header marks (CarDoor, colombia, van), so the
            // rails read as part of the bar rather than as footnotes tucked into it.
            className="h-10 w-10 shrink-0 object-contain"
            draggable={false}
          />
        </a>
      ))}
    </span>
  );
}

export default Header
