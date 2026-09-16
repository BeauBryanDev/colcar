import React from 'react'
import { FiSearch } from 'react-icons/fi'

interface ScannerAnimationProps {
  /** Preview of the image being analysed. Falls back to an empty grid. */
  imageUrl?: string
  /** Label of the stage currently running, e.g. "Análisis de llantas". */
  stageLabel?: string
  className?: string
}

/**
 * Scanning overlay shown while the backend runs vision + agent.
 *
 * Purely cosmetic: it reports that work is happening, not how far along it is.
 * Real progress comes from the /status poll and is rendered by ProcessingStatus,
 * so nothing here is tied to a percentage that could contradict it.
 */
export const ScannerAnimation: React.FC<ScannerAnimationProps> = ({
  imageUrl,
  stageLabel,
  className = '',
}) => (
  <div
    role="status"
    aria-live="polite"
    aria-label={stageLabel ? `Analizando: ${stageLabel}` : 'Analizando imagen'}
    className={[
      'relative w-full aspect-[4/3] rounded-xl overflow-hidden',
      'bg-brand-navy border-2 border-brand-blue',
      className,
    ].join(' ')}
  >
    {/* Subject */}
    {imageUrl ? (
      <img
        src={imageUrl}
        alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-70"
      />
    ) : (
      <div className="absolute inset-0 flex items-center justify-center">
        <FiSearch className="w-10 h-10 text-brand-yellow/40" aria-hidden="true" />
      </div>
    )}

    {/* Grid wash — reads as "machine vision" without obscuring the photo */}
    <div
      aria-hidden="true"
      className="absolute inset-0 opacity-25"
      style={{
        backgroundImage:
          'linear-gradient(to right, rgba(201,154,0,0.45) 1px, transparent 1px),' +
          'linear-gradient(to bottom, rgba(201,154,0,0.45) 1px, transparent 1px)',
        backgroundSize: '28px 28px',
      }}
    />

    {/* Sweep: a bright line trailing a soft glow */}
    <div
      aria-hidden="true"
      className="absolute inset-x-0 top-0 h-full motion-safe:animate-scan-sweep motion-reduce:hidden"
    >
      <div className="h-24 w-full bg-gradient-to-b from-transparent via-brand-yellow/25 to-transparent" />
      <div className="h-0.5 w-full bg-brand-yellow shadow-[0_0_12px_2px_rgba(201,154,0,0.9)]" />
    </div>

    {/* Reticle corners */}
    <div aria-hidden="true" className="absolute inset-3 motion-safe:animate-reticle-pulse">
      <span className="absolute top-0 left-0 w-6 h-6 border-t-4 border-l-4 border-brand-yellow rounded-tl-lg" />
      <span className="absolute top-0 right-0 w-6 h-6 border-t-4 border-r-4 border-brand-yellow rounded-tr-lg" />
      <span className="absolute bottom-0 left-0 w-6 h-6 border-b-4 border-l-4 border-brand-yellow rounded-bl-lg" />
      <span className="absolute bottom-0 right-0 w-6 h-6 border-b-4 border-r-4 border-brand-yellow rounded-br-lg" />
    </div>

    {/* Stage caption + indeterminate bar */}
    <div className="absolute inset-x-0 bottom-0 bg-brand-navy/85 px-3 py-2 flex flex-col gap-1.5">
      <span className="font-display text-brand-yellow text-sm tracking-widest uppercase truncate">
        {stageLabel ?? 'Analizando…'}
      </span>
      <div className="h-1 w-full bg-white/15 rounded-full overflow-hidden">
        <div className="h-full w-1/3 bg-brand-yellow rounded-full motion-safe:animate-scan-progress" />
      </div>
    </div>
  </div>
)

export default ScannerAnimation
