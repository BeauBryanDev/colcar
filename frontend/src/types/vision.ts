/**
 * Vision-stage payload — mirrors `VisionResult` in app/schemas/detections.py,
 * which is what `GET /api/inspections/{id}/results` returns under `vision`.
 *
 * Responses are camelCase (see app/schemas/common.py), so these fields are
 * the camelCase aliases of the backend's snake_case model fields.
 */

import type { Defect, PartDetection, InspectionSummaryData, Severidad, DefectSeverity } from './defect'

export type ImageRole = 'body' | 'tire'

export interface ImageMeta {
  imageId: string
  filename: string
  role: ImageRole
  width: number
  height: number
}

export interface PipelineFlags {
  tiresInspectionRequested: boolean
}

export interface VisionResult {
  inspectionId: string
  createdAt: string
  vehicleInfo: Record<string, unknown>
  pipelineFlags: PipelineFlags
  imagesAnalyzed: ImageMeta[]
  partsDetected: PartDetection[]
  surfaceDefectsDetected: Defect[]
  tireDefectsDetected: Defect[]
  /** Defects nothing contained above the 0.50 threshold — show as "ubicación no determinada". */
  unmatchedDefects: Defect[]
  summary: InspectionSummaryData
}

//  Overlay lane 
// Mirrors OverlayResponse in app/schemas/detections.py — GET /inspections/{id}/overlay.
//
// Deliberately a separate lane from the agent: polygons are hundreds of
// coordinate pairs per defect and would be re-sent on every turn of the
// tool-use loop. `to_agent_payload()` carries only `bbox_normalized`, never
// masks. Rendering data goes to the browser; the model never sees it.

export type OverlayKind = 'part' | 'defect'

export interface OverlayShape {
  detectionId: string
  imageId: string
  kind: OverlayKind
  className: string
  confidence: number
  /** xyxy in ORIGINAL image pixels. */
  bbox: [number, number, number, number]
  /** Null for tyre defects — detection-only model, no prototype masks. */
  polygon: number[][] | null
  severidad?: Severidad | null
  severidadDisplay?: DefectSeverity | null
  matchedPartName?: string | null
}

export interface OverlayImage {
  imageId: string
  filename: string
  role: ImageRole
  width: number
  height: number
  /** Relative URL served by the backend — usable directly as an <img src>. */
  imageUrl: string
  shapes: OverlayShape[]
}

export interface OverlayResponse {
  sessionId: string
  images: OverlayImage[]
}
