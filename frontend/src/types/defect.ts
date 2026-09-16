/**
 * Defect / part vocabulary — mirrors the backend, which is the source of truth.
 *
 */

//  Severity 
/**
 * Internal severity keys — the pricing catalog's own `severidad` values, which
 * the PricingTrie is keyed on. Never rename these.
 * Mirrors `Severidad` in app/schemas/common.py.
 */
export type Severidad = 'leve' | 'moderado' | 'grave'

/**
 * Display labels. Mirrors `SeveridadDisplay` in app/schemas/common.py.
 * NOTE: 'Grave', not 'Alto' — the frontend previously declared 'Alto', which
 * no backend response ever produces.
 */
export type DefectSeverity = 'Bajo' | 'Medio' | 'Grave'

export const SEVERIDAD_DISPLAY: Record<Severidad, DefectSeverity> = {
  leve: 'Bajo',
  moderado: 'Medio',
  grave: 'Grave',
}

//  Parts  

export type VehiclePart =
  | 'back_bumper'
  | 'back_door'
  | 'back_glass'
  | 'back_left_door'
  | 'back_left_light'
  | 'back_light'
  | 'back_right_door'
  | 'back_right_light'
  | 'front_bumper'
  | 'front_door'
  | 'front_glass'
  | 'front_left_door'
  | 'front_left_light'
  | 'front_light'
  | 'front_right_door'
  | 'front_right_light'
  | 'hood'
  | 'left_mirror'
  | 'object'
  | 'right_mirror'
  | 'tailgate'
  | 'trunk'
  | 'wheel'
  // Fixed `pieza` for every tyre-flow defect: no parts model runs there.
  | 'tire'

/** Spanish labels for display. `object` is dropped by app/rag/vocabulary.py and never shown. */
export const PART_DISPLAY: Record<VehiclePart, string> = {
  back_bumper: 'Parachoques trasero',
  back_door: 'Puerta trasera',
  back_glass: 'Vidrio trasero',
  back_left_door: 'Puerta trasera izquierda',
  back_left_light: 'Luz trasera izquierda',
  back_light: 'Luz trasera',
  back_right_door: 'Puerta trasera derecha',
  back_right_light: 'Luz trasera derecha',
  front_bumper: 'Parachoques delantero',
  front_door: 'Puerta delantera',
  front_glass: 'Parabrisas',
  front_left_door: 'Puerta delantera izquierda',
  front_left_light: 'Luz delantera izquierda',
  front_light: 'Luz delantera',
  front_right_door: 'Puerta delantera derecha',
  front_right_light: 'Luz delantera derecha',
  hood: 'Capó',
  left_mirror: 'Espejo izquierdo',
  object: 'Objeto',
  right_mirror: 'Espejo derecho',
  tailgate: 'Portón trasero',
  trunk: 'Baúl',
  wheel: 'Rin',
  tire: 'Llanta',
}

//   Defect classes  

/** Surface model (car_defects_model.onnx — 6 classes). */
export type SurfaceDefectClass =
  | 'crack'
  | 'dent'
  | 'glass_shatter'
  | 'lamp_broken'
  | 'scratch'
  | 'tire_flat'

/**
 * Tyre model (tyres_defect_model.onnx — 6 classes).
 * `Good` is a *positive* finding, never priced as a defect.
 */
export type TyreDefectClass =
  | 'Bulge'
  | 'Cracks'
  | 'Flat spots'
  | 'Good'
  | 'Pitting'
  | 'Puncture'

/**
 * Every defect class the pipeline can emit.
 *
 * `tire_flat` and `Flat spots` are NOT the same defect and must never be
 * aliased: `tire_flat` is a deflated tyre (pressure), `Flat spots` is a worn
 * patch on the tread (wear). Different repairs, different prices.
 */
export type DefectCategory = SurfaceDefectClass | TyreDefectClass

/** Spanish labels for display. Labels are normalised with .lower() backend-side. */
export const DEFECT_DISPLAY: Record<DefectCategory, string> = {
  crack: 'Grieta',
  dent: 'Abolladura',
  glass_shatter: 'Vidrio roto',
  lamp_broken: 'Lámpara rota',
  scratch: 'Rayón',
  tire_flat: 'Llanta desinflada',
  Bulge: 'Protuberancia',
  Cracks: 'Grietas en llanta',
  'Flat spots': 'Zonas planas',
  Good: 'Sin defecto',
  Pitting: 'Corrosión',
  Puncture: 'Pinchazo',
}

//   Detections 
/** How a severity grade was reached. Mirrors `SeverityBasisKind`. */
export type SeverityBasisKind =
  | 'part_relative'
  | 'image_relative'
  | 'legal_floor'
  | 'tyre_type_rule'

/** Mirrors `DefectDetection` in app/schemas/detections.py. */
export interface Defect {
  detectionId: string
  imageId: string
  className: DefectCategory
  confidence: number
  bbox: [number, number, number, number]
  bboxNormalized: [number, number, number, number]
  maskAreaPx?: number | null
  segmentationPolygon?: number[][] | null
  polygonFormat?: string | null

  // Spatial match — null on tyre defects, and on any surface defect nothing contained.
  matchedPartId?: string | null
  matchedPartName?: VehiclePart | null
  matchContainment?: number | null
  matchIou?: number | null
  matchBasis?: string | null

  severidad: Severidad
  severidadDisplay: DefectSeverity
  severityBasis: string
  severityBasisKind: SeverityBasisKind
  areaRatio: number
}

/** Mirrors `PartDetection` in app/schemas/detections.py. */
export interface PartDetection {
  detectionId: string
  imageId: string
  className: VehiclePart
  confidence: number
  bbox: [number, number, number, number]
  bboxNormalized: [number, number, number, number]
  maskAreaPx?: number | null
  segmentationPolygon?: number[][] | null
  polygonFormat?: string | null
}

/** Chart-friendly rollup, derived client-side from `InspectionSummary.defectsByType`. */
export interface DefectSummary {
  category: string
  count: number
  percentage: number
  color: string
}

/** Mirrors `InspectionSummary` in app/schemas/detections.py. */
export interface InspectionSummaryData {
  totalDefects: number
  defectsByType: Record<string, number>
  defectsBySeverity: Record<string, number>
  partsAffected: string[]
  unmatchedDefects: number
  tiresInspectedOk: number
}
