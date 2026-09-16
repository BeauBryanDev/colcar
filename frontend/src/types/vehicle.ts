import type { DefectSeverity } from './defect'

export type OverallStatus = 'Excelente' | 'Bueno' | 'Regular' | 'Malo' | 'Crítico'

/**
 * Optional vehicle details. Mirrors `VehicleInfo` in app/schemas/inspection.py:
 * **`brand`, not `make`** — the backend is the source of truth and the agent
 * payload has always used `brand`.
 */
export interface VehicleInfo {
  brand?: string
  model?: string
  year?: number
  color?: string
  licensePlate?: string
}

/**
 * Client-side rollup for the metrics panel.
 *
 * Costs are **COP** (integer), matching the backend's `*_cost_cop` fields —
 * this was previously commented as USD.
 */
export interface VehicleSummary {
  overallStatus: OverallStatus
  totalDefects: number
  estimatedRepairCostCop: number
  compliancePercent: number
  complianceStatus: 'Cumple' | 'No Cumple' | 'Revisar'
  partsAffected: string[]
  vehicle?: VehicleInfo
  severity: DefectSeverity
}
