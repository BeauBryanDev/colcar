/**
 * Stored inspections: filter by date / brand / RTM verdict, then open the full
 * record — defects with the evidence for their severity, the quote as priced,
 * and the agent's own narrative.
 *
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  FiAlertCircle,
  FiDollarSign,
  FiFileText,
  FiRefreshCw,
  FiShield,
} from 'react-icons/fi'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/common/Button'
import { adminService } from '@/services/adminService'
import {
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  RtmBadge,
  StatTile,
  TableSkeleton,
  formatCop,
  formatDateTime,
} from '@/components/admin/uiKit'
import type {
  InspectionDetail,
  InspectionFilters,
  InspectionSummary,
  StoredDefect,
} from '@/types/admin'

/** Internal severity keys are the pricing catalog's own; these are the labels. */
const SEVERITY_LABEL: Record<string, string> = {
  leve: 'Bajo',
  moderado: 'Medio',
  grave: 'Grave',
}

const SEVERITY_VARIANT: Record<string, 'green' | 'yellow' | 'red'> = {
  leve: 'green',
  moderado: 'yellow',
  grave: 'red',
}

export const InspectionsPage: React.FC = () => {
  const [rows, setRows] = useState<InspectionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<InspectionFilters>({})
  const [brandInput, setBrandInput] = useState('')

  const [detail, setDetail] = useState<InspectionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminService.listInspections(filters)
      setRows(data.inspections)
      setTotal(data.total)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Error cargando inspecciones.',
      )
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    void load()
  }, [load])

  const stats = useMemo(() => {
    const rejected = rows.filter((r) => r.rechazoRtmProbable === true).length
    const quoted = rows.reduce((sum, r) => sum + (r.totalCop ?? 0), 0)
    return { rejected, quoted }
  }, [rows])

  const openDetail = async (id: string) => {
    setDetailLoading(true)
    setDetail(null)
    try {
      setDetail(await adminService.getInspection(id))
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'No se pudo cargar la inspección.',
      )
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="Inspecciones"
        subtitle={`${total} inspección(es) según los filtros`}
        icon={<FiFileText className="w-6 h-6" />}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<FiRefreshCw className="w-4 h-4" />}
            onClick={() => void load()}
          >
            Actualizar
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <StatTile
          label="Inspecciones listadas"
          value={total}
          tone="navy"
          icon={<FiFileText className="w-7 h-7" />}
        />
        <StatTile
          label="Con causal de rechazo"
          value={stats.rejected}
          tone="red"
          icon={<FiShield className="w-7 h-7" />}
        />
        <StatTile
          label="Cotizado (listado)"
          value={formatCop(stats.quoted)}
          tone="yellow"
          icon={<FiDollarSign className="w-7 h-7" />}
        />
      </div>

      {/* Filters  */}
      <div className="bg-white rounded-xl border-2 border-brand-navy/10 p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Desde
            </span>
            <input
              type="date"
              value={filters.date_from ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  date_from: e.target.value || undefined,
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none"
            />
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Hasta
            </span>
            <input
              type="date"
              value={filters.date_to ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  date_to: e.target.value || undefined,
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none"
            />
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Marca
            </span>
            <input
              type="text"
              value={brandInput}
              placeholder="Renault"
              onChange={(e) => setBrandInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setFilters((f) => ({ ...f, brand: brandInput || undefined }))
                }
              }}
              onBlur={() =>
                setFilters((f) => ({ ...f, brand: brandInput || undefined }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none"
            />
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Veredicto RTM
            </span>
            <select
              value={
                filters.rechazo_rtm_probable === undefined
                  ? ''
                  : String(filters.rechazo_rtm_probable)
              }
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  rechazo_rtm_probable:
                    e.target.value === '' ? undefined : e.target.value === 'true',
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none bg-white"
            >
              <option value="">Todos</option>
              <option value="true">No cumple</option>
              <option value="false">Cumple</option>
            </select>
          </label>
        </div>
        {(filters.date_from ||
          filters.date_to ||
          filters.brand ||
          filters.rechazo_rtm_probable !== undefined) && (
          <button
            type="button"
            className="mt-3 text-brand-blue text-sm font-semibold hover:underline"
            onClick={() => {
              setFilters({})
              setBrandInput('')
            }}
          >
            Limpiar filtros
          </button>
        )}
      </div>

      {/* Table  */}
      <div className="bg-white rounded-xl border-2 border-brand-navy/10 overflow-hidden">
        {loading ? (
          <div className="px-4">
            <TableSkeleton />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState message={error} onRetry={() => void load()} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            message="No hay inspecciones con estos filtros"
            hint="Las inspecciones se guardan al completarse el análisis."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brand-navy text-white">
                <tr>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Fecha
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Vehículo
                  </th>
                  <th className="text-center px-4 py-2.5 font-display tracking-wider uppercase">
                    Defectos
                  </th>
                  <th className="text-right px-4 py-2.5 font-display tracking-wider uppercase">
                    Total
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    RTM
                  </th>
                  <th className="text-right px-4 py-2.5 font-display tracking-wider uppercase">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.inspectionId}
                    className="border-b border-brand-navy/10 hover:bg-brand-yellow/10 transition-colors"
                  >
                    <td className="px-4 py-3 text-brand-navy whitespace-nowrap">
                      {formatDateTime(row.createdAt)}
                    </td>
                    <td className="px-4 py-3 text-brand-navy">
                      <div className="font-semibold">
                        {[row.brand, row.vehicleModel, row.year]
                          .filter(Boolean)
                          .join(' ') || '—'}
                      </div>
                      <div className="text-brand-navy/50 text-xs">
                        {row.imagesAnalyzed} imagen(es) · {row.status}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center font-semibold text-brand-navy">
                      {row.defectCount}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-brand-navy whitespace-nowrap">
                      {formatCop(row.totalCop)}
                    </td>
                    <td className="px-4 py-3">
                      <RtmBadge rejected={row.rechazoRtmProbable} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => void openDetail(row.inspectionId)}
                      >
                        Ver informe
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail  */}
      {(detail || detailLoading) && (
        <Modal
          title="Informe de inspección"
          wide
          onClose={() => setDetail(null)}
        >
          {detailLoading || !detail ? (
            <TableSkeleton rows={6} />
          ) : (
            <div className="space-y-5 text-brand-navy">
              <div className="flex flex-wrap items-center gap-3">
                <RtmBadge rejected={detail.rechazoRtmProbable} />
                <Badge variant="navy">{detail.status}</Badge>
                <span className="font-display text-2xl">
                  {formatCop(detail.totalCop)}
                </span>
                <span className="text-brand-navy/50 text-xs">
                  {formatDateTime(detail.createdAt)}
                </span>
              </div>

              {detail.rechazoRtmProbable === true && (
                <div className="flex items-start gap-2 bg-brand-red/15 border-2 border-brand-red/50 rounded-lg px-3 py-2.5">
                  <FiAlertCircle className="w-5 h-5 text-brand-red flex-shrink-0 mt-0.5" />
                  <p className="text-sm font-semibold">
                    Este vehículo presenta al menos una causal de rechazo en la
                    RTM. El resultado es No Cumple, no un porcentaje.
                  </p>
                </div>
              )}

              {/* Defects, with the audit fields that make a surprising quote
                  explainable months later. */}
              <div>
                <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-2">
                  Defectos ({detail.defects.length})
                </h3>
                {detail.defects.length === 0 ? (
                  <p className="text-brand-navy/50 text-sm">
                    Sin defectos registrados.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-brand-navy/5">
                        <tr>
                          <th className="text-left px-2 py-1.5">Pieza</th>
                          <th className="text-left px-2 py-1.5">Defecto</th>
                          <th className="text-left px-2 py-1.5">Severidad</th>
                          <th className="text-right px-2 py-1.5">Precio</th>
                          <th className="text-left px-2 py-1.5">RTM</th>
                          <th className="text-left px-2 py-1.5">Base</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.defects.map((d: StoredDefect, i) => (
                          <tr key={i} className="border-b border-brand-navy/10">
                            <td className="px-2 py-1.5 font-mono">{d.pieza}</td>
                            <td className="px-2 py-1.5 font-mono">
                              {d.tipo_defecto}
                            </td>
                            <td className="px-2 py-1.5">
                              <Badge
                                variant={
                                  SEVERITY_VARIANT[d.severidad] ?? 'gray'
                                }
                              >
                                {SEVERITY_LABEL[d.severidad] ?? d.severidad}
                              </Badge>
                            </td>
                            <td className="px-2 py-1.5 text-right whitespace-nowrap">
                              {formatCop(d.total_cost_cop)}
                              {d.precio_exacto === false && (
                                <span
                                  className="text-brand-navy/50"
                                  title="Estimado por categoría, no es precio exacto"
                                >
                                  {' '}
                                  ≈
                                </span>
                              )}
                            </td>
                            <td className="px-2 py-1.5">
                              {d.causal_rechazo ? (
                                <Badge variant="red">
                                  Causal {d.clase_rechazo ?? ''}
                                </Badge>
                              ) : (
                                <span className="text-brand-navy/40">—</span>
                              )}
                            </td>
                            {/* severity_basis is why this grade was given —
                                what makes an odd quote auditable. */}
                            <td className="px-2 py-1.5 font-mono text-brand-navy/50">
                              {d.severity_basis ?? '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {detail.resumenAgente && (
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-2">
                    Diagnóstico del agente
                  </h3>
                  <div className="prose prose-sm max-w-none bg-brand-navy/5 rounded-lg p-3 [&_table]:w-full [&_th]:text-left [&_th]:font-semibold [&_td]:py-0.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {detail.resumenAgente}
                    </ReactMarkdown>
                  </div>
                </div>
              )}

              <details className="bg-brand-navy/5 rounded-lg p-3">
                <summary className="cursor-pointer font-display tracking-wider uppercase text-sm text-brand-navy/60">
                  Datos crudos (cotización y normativa)
                </summary>
                <pre className="mt-2 text-xs overflow-x-auto">
                  {JSON.stringify(
                    {
                      pricing: detail.pricing,
                      compliance: detail.compliance,
                      vehicle_info: detail.vehicleInfo,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>

              <p className="text-brand-navy/50 text-xs">
                ID: <span className="font-mono">{detail.inspectionId}</span>
              </p>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}

export default InspectionsPage
