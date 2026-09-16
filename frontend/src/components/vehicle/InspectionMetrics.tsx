import React from 'react'
import { FiShield } from 'react-icons/fi'
import type { VehicleSummary } from '@/types'
import carIconUrl from '@/assets/car_icon.svg'

interface InspectionMetricsProps {
  /** Null until the backend has produced real figures. */
  summary?: VehicleSummary | null
}

const statusColor: Record<VehicleSummary['overallStatus'], string> = {
  Excelente: 'text-emerald-500',
  Bueno:     'text-green-500',
  Regular:   'text-brand-yellow',
  Malo:      'text-orange-500',
  Crítico:   'text-brand-red',
}

export const InspectionMetrics: React.FC<InspectionMetricsProps> = ({ summary }) => {
  // No fabricated placeholders: an invented repair cost is indistinguishable
  // from a real quote to the customer reading it.
  const data = summary

  return (
    <div className="flex flex-col gap-3">
      {/* Section title */}
      <div className="flex items-center gap-2">
        <img src={carIconUrl} alt="" className="w-6 h-6 opacity-80" aria-hidden="true" />
        <h3 className="font-display text-brand-navy tracking-widest uppercase text-lg">
          RESUMEN DEL VEHÍCULO
        </h3>
      </div>

      {!data && (
        <p className="text-brand-navy text-base leading-snug">
          Aún no hay resultados. Sube una imagen y pulsa Analizar.
        </p>
      )}

      {/* Metrics row */}
      {data && (
      <div className="grid grid-cols-4 gap-2">
        {/* Overall status */}
        <div className="col-span-1 flex flex-col items-center justify-center gap-1 bg-brand-navy/10 rounded-xl p-3 border border-brand-navy/20">
          <FiShield className="w-6 h-6 text-brand-navy" />
          <span className="text-sm font-bold text-brand-navy uppercase tracking-wide text-center">
            Estado General
          </span>
          <span className={`font-extrabold text-base ${statusColor[data.overallStatus]}`}>
            {data.overallStatus.toUpperCase()}
          </span>
        </div>

        {/* Total defects */}
        <div className="flex flex-col items-center justify-center gap-0.5 bg-brand-navy/10 rounded-xl p-3 border border-brand-navy/20">
          <span className="text-brand-red font-display text-3xl leading-none">
            {data.totalDefects}
          </span>
          <span className="text-sm text-brand-navy font-semibold uppercase text-center leading-tight">
            Defectos
            <br />
            Totales
          </span>
          <span className="text-sm text-brand-navy">Detectados</span>
        </div>

        {/* Repair cost */}
        <div className="flex flex-col items-center justify-center gap-0.5 bg-brand-navy/10 rounded-xl p-3 border border-brand-navy/20">
          <span className="text-brand-navy font-display text-2xl leading-none">
            ${data.estimatedRepairCostCop.toLocaleString('es-CO')}
          </span>
          <span className="text-sm text-brand-navy font-semibold uppercase text-center leading-tight">
            Costo Est.
            <br />
            Reparación
          </span>
          <span className="text-sm text-brand-navy">COP</span>
        </div>

        {/* Compliance */}
        <div className="flex flex-col items-center justify-center gap-0.5 bg-brand-navy/10 rounded-xl p-3 border border-brand-navy/20">
          <span
            className={[
              'font-display text-3xl leading-none',
              data.complianceStatus === 'Cumple' ? 'text-emerald-600' : 'text-brand-red',
            ].join(' ')}
          >
            {data.compliancePercent}%
          </span>
          <span className="text-sm text-brand-navy font-semibold uppercase text-center leading-tight">
            Cumplimiento
          </span>
          <span
            className={[
              'text-sm font-bold',
              data.complianceStatus === 'Cumple' ? 'text-emerald-600' : 'text-brand-red',
            ].join(' ')}
          >
            {data.complianceStatus}
          </span>
        </div>
      </div>
      )}
    </div>
  )
}

export default InspectionMetrics
