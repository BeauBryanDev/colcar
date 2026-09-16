/**
 * The agent's report, exactly as `GET /inspections/{id}/results` returns it.
 *
 * This is NOT `app/schemas/defects.py::InspectionReport`. That model exists
 * but the router never builds it — `_execute_pipeline` assembles a plain dict:
 *
 *     {resumen, pricing, compliance, tools_used}
 *
 * and `InspectionResultResponse.report` is typed `dict[str, Any]`. Pydantic's
 * camelCase alias generator only renames *model fields*, so everything nested
 * inside this dict stays **snake_case** on the wire (`total_cop`, not
 * `totalCop`). Verified against a live run.
 *
 * Currency is integer COP throughout.
 */

import type { Severidad } from './defect'

// Pricing (result of the query_pricing_batch tool)

export type FallbackLevel = 'exact' | 'part+defect_generic' | 'part_generic' | 'not_found'

export interface PricingEntry {
  service_name: string
  labor_hours: number
  labor_cost_cop: number
  materials_cost_cop: number
  parts_cost_cop: number
  total_cost_cop: number
  requires_replacement: boolean
}

export interface PricingItem {
  pieza: string
  tipo_defecto: string
  severidad: Severidad
  exact_match: boolean
  fallback_level: FallbackLevel
  entry: PricingEntry | null
  cantidad: number
  precio_exacto: boolean
  nota: string
  subtotal_cop: number
}

/** `total_cop` is summed in Python — never re-sum it in the SPA. */
export interface PricingSummary {
  total_cop: number
  subtotal_mano_obra_cop: number
  subtotal_materiales_cop: number
  subtotal_repuestos_cop: number
  items_con_precio_exacto: number
  items_estimados: number
  /** Defects with no catalog price. Excluded from the total — never render as 0. */
  items_sin_precio: string[]
  requieren_reemplazo: string[]
  moneda: string
  marca?: string | null
  indice_marca?: number | null
}

export interface PricingResult {
  items: PricingItem[]
  resumen: PricingSummary
  instrucciones: string
}

// Compliance (result of the query_compliance tool)

export interface ComplianceNorm {
  norma?: string
  documento_id?: string
  articulo?: string | null
  seccion?: string | null
  severidad?: string | null
  binding?: boolean
  texto?: string
  score?: number
}

/**
 * `aplica_rtm: false` means the standard does not cover this defect — it is
 * **not** a rejection cause. That is different from `normas: []`, which means
 * the defect is in scope but nothing was retrieved.
 */
export interface ComplianceResult {
  pieza: string
  tipo_defecto: string
  aplica_rtm: boolean
  /**
   * Whether this defect fails the RTM. Decided server-side in
   * `app/rag/rtm_rules.py`, not inferred from `normas.length` — defects on the
   * legal floor (lamp_broken, glass_shatter) reject the vehicle even when
   * retrieval returns nothing.
   */
  causal_rechazo: boolean
  /** 'A' (critical) or 'B' from the NTC 5375 defect tables. */
  clase_rechazo: string | null
  normas: ComplianceNorm[]
  nota: string
}

export interface ComplianceReport {
  resultados: ComplianceResult[]
  /** Pre-computed verdict: true when any defect is a rejection cause. */
  rechazo_rtm_probable: boolean
  defectos_causal_rechazo: string[]
  instrucciones: string
}

// The report

export interface InspectionReport {
  /** The agent's customer-facing narrative, in Spanish markdown. */
  resumen: string
  pricing: PricingResult | null
  compliance: ComplianceReport | null
  tools_used: string[]
}

// Chat

export type MessageRole = 'agent' | 'user' | 'system'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  isTyping?: boolean
}
