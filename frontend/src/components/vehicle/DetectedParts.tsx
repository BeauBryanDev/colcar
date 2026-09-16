import React, { useMemo } from 'react'
import type { VehiclePart, VisionResult } from '@/types'
import { PART_DISPLAY } from '@/types'

/**
 * The car parts the segmentation model found, and which of them carry damage.
 *
 * Shown because a part list is how the customer checks the system looked at the
 * right car: "it found my hood, both doors and the left headlight" is legible
 * in a way a mask overlay alone is not.
 *
 * `object` is the parts model's catch-all and is dropped project-wide
 * (`IGNORED_PART_CLASSES`), so it never appears here either.
 */

interface DetectedPartsProps {
  vision: VisionResult | null
  className?: string
}

interface PartRow {
  name: string
  display: string
  count: number
  /** Best confidence among detections of this class. */
  confidence: number
  affected: boolean
}

export const DetectedParts: React.FC<DetectedPartsProps> = ({ vision, className = '' }) => {
  const rows = useMemo<PartRow[]>(() => {
    const parts = vision?.partsDetected ?? []
    if (!parts.length) return []

    // `partsAffected` is the summary's list of parts a defect was attributed to.
    const affected = new Set(vision?.summary?.partsAffected ?? [])

    const byClass = new Map<string, PartRow>()
    for (const p of parts) {
      if (p.className === 'object') continue
      const existing = byClass.get(p.className)
      if (existing) {
        existing.count += 1
        existing.confidence = Math.max(existing.confidence, p.confidence)
      } else {
        byClass.set(p.className, {
          name: p.className,
          display: PART_DISPLAY[p.className as VehiclePart] ?? p.className,
          count: 1,
          confidence: p.confidence,
          affected: affected.has(p.className),
        })
      }
    }

    // Damaged parts first — that is what the customer is looking for.
    return [...byClass.values()].sort((a, b) => {
      if (a.affected !== b.affected) return a.affected ? -1 : 1
      return b.confidence - a.confidence
    })
  }, [vision])

  if (!rows.length) {
    return (
      <div className={className}>
        <h3 className="font-extrabold text-brand-navy uppercase text-base tracking-wide mb-2">
          PIEZAS DETECTADAS
        </h3>
        <p className="text-brand-navy text-base leading-snug">
          Aún no se han detectado piezas.
        </p>
      </div>
    )
  }

  const damaged = rows.filter((r) => r.affected).length

  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <h3 className="font-extrabold text-brand-navy uppercase text-base tracking-wide">
          PIEZAS DETECTADAS
        </h3>
        <span className="text-brand-navy text-sm font-semibold">
          {rows.length} pieza{rows.length !== 1 ? 's' : ''}
          {damaged > 0 && ` · ${damaged} con daño`}
        </span>
      </div>

      <ul className="flex flex-wrap gap-1.5">
        {rows.map((r) => (
          <li
            key={r.name}
            title={`${r.display} — confianza ${(r.confidence * 100).toFixed(0)}%`}
            className={[
              'flex items-center gap-1.5 rounded-lg border px-2 py-1 text-sm font-semibold',
              r.affected
                ? 'bg-brand-red/10 border-brand-red text-brand-red'
                : 'bg-brand-navy/5 border-brand-navy/25 text-brand-navy',
            ].join(' ')}
          >
            <span
              aria-hidden="true"
              className={[
                'w-1.5 h-1.5 rounded-full',
                r.affected ? 'bg-brand-red' : 'bg-emerald-600',
              ].join(' ')}
            />
            <span>{r.display}</span>
            {r.count > 1 && <span className="opacity-70">×{r.count}</span>}
            <span className="opacity-60 tabular-nums">
              {(r.confidence * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>

      <p className="text-brand-navy text-sm mt-1.5 leading-snug">
        Rojo: pieza con daño detectado. Verde: pieza detectada sin daño.
      </p>
    </div>
  )
}

export default DetectedParts
