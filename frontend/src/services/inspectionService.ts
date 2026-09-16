import apiClient from './api'
import type {
  DetectionModel,
  InspectionSession,
  ProcessingStep,
  VehicleSelection,
  OverlayResponse,
} from '@/types'

// ─── Payload / response shapes ──────────────────────────────────────────────

interface StartInspectionResponse {
  sessionId: string
  message: string
}

interface UploadFilesResponse {
  sessionId: string
  uploadedCount: number
  message: string
}

interface ProcessingStatusResponse {
  sessionId: string
  steps: ProcessingStep[]
  overallStatus: InspectionSession['status']
}

// ─── Agent actions ───────────────────────────────────────────────────────────

export type AgentAction = 'estimate_costs' | 'verify_compliance' | 'explain_defects'

/** Spanish prompts for the three action buttons — the agent replies in Spanish. */
const ACTION_PROMPTS: Record<AgentAction, string> = {
  estimate_costs:
    'Dame el desglose completo de la cotización de reparación en COP, ítem por ítem.',
  verify_compliance:
    '¿Alguno de estos defectos es causa de rechazo en la revisión técnico-mecánica (RTM)? Cita las normas aplicables.',
  explain_defects:
    'Explícame en detalle cada defecto detectado, su gravedad y por qué se calificó así.',
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const inspectionService = {
  /**
   * Create a new inspection session.
   *
   * `vehicle_info` is snake_case per app/schemas/common.py, and uses `brand`
   * (not `make`) — the backend's agent payload has always used `brand`.
   */
  async startSession(vehicle?: VehicleSelection): Promise<StartInspectionResponse> {
    const body =
      vehicle && (vehicle.brand || vehicle.vehicleModel || vehicle.year)
        ? {
            vehicle_info: {
              brand: vehicle.brand ?? undefined,
              model: vehicle.vehicleModel ?? undefined,
              year: vehicle.year ?? undefined,
            },
          }
        : {}

    const res = await apiClient.post<StartInspectionResponse>('/inspections/start', body)
    return res.data
  },

  /**
   * Upload files for a specific detection model.
   *
   * `vehicle` is sent as the `brand` / `vehicle_model` / `year` form fields —
   * `vehicle_model`, not `model`, because `model` already names the detection
   * panel. The brand selects the price index server-side, so an unrecognised
   * or omitted value quotes at baseline rather than erroring.
   */
  async uploadFiles(
    sessionId: string,
    model: DetectionModel,
    files: File[],
    vehicle?: VehicleSelection,
    onProgress?: (percent: number) => void,
  ): Promise<UploadFilesResponse> {
    const form = new FormData()
    form.append('session_id', sessionId)
    form.append('model', model)
    files.forEach((f) => form.append('files', f))

    if (vehicle?.brand) form.append('brand', vehicle.brand)
    if (vehicle?.vehicleModel) form.append('vehicle_model', vehicle.vehicleModel)
    if (vehicle?.year != null) form.append('year', String(vehicle.year))

    const res = await apiClient.post<UploadFilesResponse>('/inspections/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) {
          onProgress(Math.round((evt.loaded / evt.total) * 100))
        }
      },
    })
    return res.data
  },

  /** Kick off YOLO + LLM processing */
  async runInspection(sessionId: string): Promise<{ message: string }> {
    const res = await apiClient.post<{ message: string }>('/inspections/run', { session_id: sessionId })
    return res.data
  },

  /**
   * Segmentation masks for rendering, without the rest of the vision payload.
   *
   * A separate call from `/results` on purpose — this is the browser's
   * rendering lane. The agent's payload never contains polygons.
   */
  async getOverlay(sessionId: string): Promise<OverlayResponse> {
    const res = await apiClient.get<OverlayResponse>(`/inspections/${sessionId}/overlay`)
    return res.data
  },

  /** Poll processing step status */
  async getProcessingStatus(sessionId: string): Promise<ProcessingStatusResponse> {
    const res = await apiClient.get<ProcessingStatusResponse>(
      `/inspections/${sessionId}/status`,
    )
    return res.data
  },

  /**
   * Start a chat-only session for a returning customer who wants to read,
   * move or cancel a booking. No photos, no vision run; /chat works as usual.
   */
  async startAppointmentChat(): Promise<StartInspectionResponse> {
    const res = await apiClient.post<StartInspectionResponse>('/inspections/appointment-chat/start')
    return res.data
  },

  /** Send a chat message to Car-Lens */
  async sendChatMessage(
    sessionId: string,
    message: string,
  ): Promise<{ reply: string; timestamp: string }> {
    const res = await apiClient.post<{ reply: string; timestamp: string }>(
      '/inspections/chat',
      { session_id: sessionId, message },
    )
    return res.data
  },

  /**
   * The three agent action buttons.
   *
   * There is no `/inspections/action` endpoint — the backend exposes only
   * `/inspections/chat`, and the agent already holds the inspection in its
   * memory window, so an action is just a scripted question on the same thread.
   */
  async triggerAction(
    sessionId: string,
    action: AgentAction,
  ): Promise<{ reply: string; timestamp: string }> {
    return inspectionService.sendChatMessage(sessionId, ACTION_PROMPTS[action])
  },
}
