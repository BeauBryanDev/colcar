import React from 'react'
import { FiPlay, FiLoader } from 'react-icons/fi'
import { useInspection } from '@/hooks/useInspection'
import type { DetectionModel } from '@/types'

/** What each panel actually runs on the backend. */
const FLOW_LABEL: Record<DetectionModel, string> = {
  vehicle_parts: 'Partes del vehículo',
  surface_defects: 'Partes + defectos de superficie (2 modelos de segmentación)',
  tires_wheels: 'Defectos de llantas (1 modelo de detección)',
}

/**
 * The submit control below the drop zones — this is what signals the backend:
 * start session → upload → run → poll.
 */
export const SubmitAnalysis: React.FC = () => {
  const { startInspection, canSubmit, isBusy, totalFiles, activeModel, status } = useInspection()

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        disabled={!canSubmit}
        onClick={() => void startInspection()}
        className={[
          'group relative w-full flex items-center justify-center gap-3',
          'rounded-xl border-4 border-brand-blue',
          'bg-brand-yellow text-brand-blue',
          'px-5 py-3.5',
          'font-display text-2xl uppercase tracking-[0.2em]',
          'shadow-[0_4px_0_0_#1a3a6e] transition-all duration-150',
          'focus:outline-none focus:ring-4 focus:ring-brand-blue/40',
          // Pressed: drop into the shadow instead of floating above it.
          canSubmit
            ? 'hover:bg-brand-gold hover:-translate-y-0.5 hover:shadow-[0_6px_0_0_#1a3a6e] active:translate-y-1 active:shadow-[0_1px_0_0_#1a3a6e] cursor-pointer'
            : 'opacity-50 cursor-not-allowed shadow-[0_4px_0_0_#1a3a6e]',
        ].join(' ')}
      >
        {isBusy ? (
          <FiLoader className="w-6 h-6 animate-spin flex-shrink-0" aria-hidden="true" />
        ) : (
          <FiPlay className="w-6 h-6 fill-brand-blue flex-shrink-0" aria-hidden="true" />
        )}
        <span>{isBusy ? 'Analizando…' : 'Analizar'}</span>
      </button>

      {/* Why the button is doing what it is doing */}
      {totalFiles === 0 && (
        <p className="text-brand-navy/70 text-xs text-center leading-snug">
          Sube al menos una imagen en uno de los dos paneles.
        </p>
      )}

      {totalFiles > 0 && activeModel && !isBusy && (
        <p className="text-brand-navy/70 text-xs text-center leading-snug">
          {totalFiles} archivo{totalFiles !== 1 ? 's' : ''} · {FLOW_LABEL[activeModel]}
        </p>
      )}

      {status === 'error' && (
        <p className="text-brand-red text-xs text-center font-semibold leading-snug">
          Ocurrió un error durante el análisis. Intenta de nuevo.
        </p>
      )}
    </div>
  )
}

export default SubmitAnalysis
