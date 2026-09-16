import type { Defect } from './defect'
import type { VehicleSummary } from './vehicle'

// Detection model types — matches DetectionModel in app/schemas/common.py
export type DetectionModel =
  | 'vehicle_parts'   // Detección de Vehículo y Partes
  | 'surface_defects' // Detección de Defectos en Superficies
  | 'tires_wheels'    // Detección de Llantas y Ruedas

export type InspectionStatus =
  | 'idle'
  | 'uploading'
  | 'processing'
  | 'analyzing'
  | 'complete'
  | 'error'

export interface ProcessingStep {
  id: string
  label: string
  status: 'pending' | 'running' | 'done' | 'error'
  completedAt?: string
}

export interface UploadedFile {
  id: string
  name: string
  size: number
  type: string                  // MIME type
  model: DetectionModel
  preview?: string              // object URL for images
  uploadedAt: string
  /**
   * The real File handle from the drop/picker. Required: the multipart upload
   * sends *this*, and it cannot be reconstructed from the metadata above —
   * rebuilding it as `new File([], name)` posts a zero-byte file that the
   * backend accepts and then finds no vehicle in.
   */
  file: File
}

export interface InspectionSession {
  id: string
  /** 'appointment' = chat-only session to read, move or cancel a booking. */
  mode?: 'inspection' | 'appointment'
  status: InspectionStatus
  uploadedFiles: UploadedFile[]
  processingSteps: ProcessingStep[]
  defects: Defect[]
  summary?: VehicleSummary
  startedAt: string
  completedAt?: string
  error?: string
}
