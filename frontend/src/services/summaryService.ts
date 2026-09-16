/**
 * Derives the dashboard figures from real backend data.
 *
 * Every number here traces to the payload — nothing is invented. Where the
 * backend has not produced a value yet, the caller gets `null` and renders an
 * empty state, because a plausible-looking placeholder in a repair quote is
 * worse than a blank: the customer cannot tell the two apart.
 */

import type {
  DefectSummary,
  InspectionReport,
  OverallStatus,
  VehicleSummary,
  VisionResult,
  DefectSeverity,
} from '@/types'
import { DEFECT_DISPLAY } from '@/types'

/** Chart colours, stable per defect class so the legend never shuffles. */
const TYPE_COLORS: Record<string, string> = {
  dent: '#cc1f1f',
  scratch: '#1a3a6e',
  crack: '#c99a00',
  glass_shatter: '#a855f7',
  lamp_broken: '#f97316',
  tire_flat: '#0891b2',
  Bulge: '#e11d48',
  Cracks: '#c99a00',
  'Flat spots': '#7c3aed',
  Pitting: '#65a30d',
  Puncture: '#0891b2',
  Good: '#16a34a',
}
const FALLBACK_COLORS = ['#cc1f1f', '#1a3a6e', '#c99a00', '#f97316', '#a855f7', '#0891b2']

/**
 * Worst severity present drives the headline status. `defectsBySeverity` keys
 * are the internal catalog values (leve/moderado/grave).
 */
function overallStatusFrom(bySeverity: Record<string, number>, total: number): OverallStatus {
  if (total === 0) return 'Excelente'
  const grave = bySeverity.grave ?? 0
  const moderado = bySeverity.moderado ?? 0
  if (grave >= 3) return 'Crítico'
  if (grave >= 1) return 'Malo'
  if (moderado >= 1) return 'Regular'
  return 'Bueno'
}

function worstSeverity(bySeverity: Record<string, number>): DefectSeverity {
  if ((bySeverity.grave ?? 0) > 0) return 'Grave'
  if ((bySeverity.moderado ?? 0) > 0) return 'Medio'
  return 'Bajo'
}

/** Defect-type breakdown for the chart, straight from `vision.summary.defectsByType`. */
export function deriveDefectsByType(vision: VisionResult | null): DefectSummary[] {
  const byType = vision?.summary?.defectsByType
  if (!byType) return []

  const total = Object.values(byType).reduce((sum, n) => sum + n, 0)
  if (total === 0) return []

  return Object.entries(byType)
    .sort(([, a], [, b]) => b - a)
    .map(([className, count], i) => ({
      category: DEFECT_DISPLAY[className as keyof typeof DEFECT_DISPLAY] ?? className,
      count,
      percentage: Math.round((count / total) * 100),
      color: TYPE_COLORS[className] ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length],
    }))
}

/**
 * RTM compliance.
 *
 * `aplica_rtm: false` means the standard does not cover the defect, which is
 * **not** a rejection cause — treating it as one would tell a customer their
 * scratched bumper fails inspection. Only a defect that is in scope *and*
 * returned norms counts against compliance.
 */
function deriveCompliance(report: InspectionReport | null): {
  percent: number
  status: VehicleSummary['complianceStatus']
} {
  const results = report?.compliance?.resultados
  if (!results?.length) {
    // Nothing checked yet: do not claim a pass.
    return { percent: 0, status: 'Revisar' }
  }

  // Trust the backend's verdict rather than re-deriving it here. `rtm_rules.py`
  // owns that decision so the SPA and the agent can never disagree about
  // whether a car passes — and it accounts for the legal floor, where a defect
  // rejects even with no clause retrieved.
  const failing =
    report?.compliance?.rechazo_rtm_probable ??
    results.some((r) => r.causal_rechazo)

  // RTM is pass/fail, not a ratio. One rejection cause fails the whole
  // inspection: a car with a broken headlight does not "67% comply".
  if (failing) return { percent: 0, status: 'No Cumple' }

  // In scope and clean, or entirely out of RTM scope (cosmetic damage only).
  return { percent: 100, status: 'Cumple' }
}

/**
 * The metrics panel's figures. Returns null before there is anything real to
 * show, so the UI renders an empty state rather than fabricated numbers.
 */
export function deriveVehicleSummary(
  vision: VisionResult | null,
  report: InspectionReport | null,
): VehicleSummary | null {
  if (!vision?.summary) return null

  const { totalDefects, defectsBySeverity } = vision.summary
  const compliance = deriveCompliance(report)

  return {
    overallStatus: overallStatusFrom(defectsBySeverity ?? {}, totalDefects),
    totalDefects,
    // Summed in Python; the SPA only displays it.
    estimatedRepairCostCop: report?.pricing?.resumen?.total_cop ?? 0,
    compliancePercent: compliance.percent,
    complianceStatus: compliance.status,
    partsAffected: vision.summary.partsAffected ?? [],
    severity: worstSeverity(defectsBySeverity ?? {}),
  }
}

/** Defects the catalog could not price — excluded from the total, quoted manually. */
export function unpricedItems(report: InspectionReport | null): string[] {
  return report?.pricing?.resumen?.items_sin_precio ?? []
}
