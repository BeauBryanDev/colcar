import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import type {
  InspectionSession,
  InspectionStatus,
  UploadedFile,
  ProcessingStep,
  DetectionModel,
  ChatMessage,
  InspectionReport,
  VehicleSelection,
  VehicleSummary,
  VisionResult,
  OverlayResponse,
  Defect,
} from '@/types'

// Interfaces 

interface UploadState {
  // Per-model upload files
  files: Record<DetectionModel, UploadedFile[]>
  dragOver: Record<DetectionModel, boolean>
}

interface ChatState {
  messages: ChatMessage[]
  isAgentTyping: boolean
  inputValue: string
}

interface ReportState {
  report: InspectionReport | null
  isLoadingReport: boolean
  /** Raw vision payload — matches, severity bases, summary. */
  vision: VisionResult | null
  /** Rendering lane: masks + served image URLs. Never sent to the agent. */
  overlay: OverlayResponse | null
}

interface AppState {
  // Session
  session: InspectionSession | null
  status: InspectionStatus

  // Brand / model / year from the three selects. `brand` scales the quote
  // server-side, so it must reach the first upload call.
  vehicle: VehicleSelection

  // Upload
  upload: UploadState

  // Chat
  chat: ChatState

  // Report / results
  report: ReportState

  // UI
  activeTab: 'inspector' | 'report'

  // Actions  
  // Session
  startSession: () => void
  /** Replace the placeholder id with the real one returned by POST /inspections/start. */
  setSessionId: (sessionId: string) => void
  /** Chat-only session from POST /inspections/appointment-chat/start. */
  startAppointmentSession: (sessionId: string) => void
  resetSession: () => void
  setStatus: (status: InspectionStatus) => void

  setVehicle: (vehicle: VehicleSelection) => void

  // Upload
  addFile: (model: DetectionModel, file: UploadedFile) => void
  removeFile: (model: DetectionModel, fileId: string) => void
  setDragOver: (model: DetectionModel, isDragging: boolean) => void
  clearFiles: (model: DetectionModel) => void

  // Processing steps
  setProcessingSteps: (steps: ProcessingStep[]) => void
  updateStep: (stepId: string, status: ProcessingStep['status']) => void

  // Chat
  addMessage: (msg: ChatMessage) => void
  setAgentTyping: (typing: boolean) => void
  setInputValue: (val: string) => void
  clearMessages: () => void

  // Results
  setSummary: (summary: VehicleSummary) => void
  setDefects: (defects: Defect[]) => void
  setReport: (report: InspectionReport | null) => void
  setLoadingReport: (loading: boolean) => void
  setVision: (vision: VisionResult | null) => void
  setOverlay: (overlay: OverlayResponse | null) => void

  // UI
  setActiveTab: (tab: 'inspector' | 'report') => void
}

//  Default processing steps matching the mockup  

/**
 * Mirrors STEP_DEFINITIONS in app/core/session.py — ids must match exactly or
 * the /status poll can never advance the UI. These are only the placeholders
 * shown before the first poll; the poll then replaces the list wholesale.
 */
const DEFAULT_PROCESSING_STEPS: ProcessingStep[] = [
  { id: 'upload',         label: 'Carga de imágenes',                   status: 'pending' },
  { id: 'vision_parts',   label: 'Detección de piezas del vehículo',    status: 'pending' },
  { id: 'vision_defects', label: 'Detección de defectos en superficie', status: 'pending' },
  { id: 'vision_tires',   label: 'Análisis de llantas',                 status: 'pending' },
  { id: 'spatial_match',  label: 'Cruce de defectos con piezas',        status: 'pending' },
  { id: 'agent',          label: 'Diagnóstico, cotización y normativa', status: 'pending' },
]

/**
 * Per-panel image cap, mirroring `settings.max_images_surface` /
 * `max_images_tyres` in `app/core/config.py`. The tyre flow takes exactly one
 * image. Raising a value here without raising it there only moves the
 * rejection server-side.
 */
export const MAX_FILES_PER_MODEL: Record<DetectionModel, number> = {
  vehicle_parts: 2,
  surface_defects: 2,
  tires_wheels: 1,
}

const EMPTY_FILES: Record<DetectionModel, UploadedFile[]> = {
  vehicle_parts: [],
  surface_defects: [],
  tires_wheels: [],
}

const EMPTY_DRAG: Record<DetectionModel, boolean> = {
  vehicle_parts: false,
  surface_defects: false,
  tires_wheels: false,
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useInspectionStore = create<AppState>()(
  devtools(
    (set) => ({
      // ── Initial state ────────────────────────────────────────────────────
      session: null,
      status: 'idle',

      vehicle: { brand: null, vehicleModel: null, year: null },

      upload: {
        files: { ...EMPTY_FILES },
        dragOver: { ...EMPTY_DRAG },
      },

      chat: {
        messages: [
          {
            id: 'welcome',
            role: 'agent',
            content:
              '¡Hola! Soy Car-Lens, tu agente de inspección con IA. Sube imágenes o videos de tu vehículo y analizaré su estado, detectaré defectos, estimaré costos de reparación y verificaré el cumplimiento con el Ministerio de Transporte.',
            timestamp: new Date().toLocaleTimeString('es-MX', {
              hour: '2-digit',
              minute: '2-digit',
            }),
          },
        ],
        isAgentTyping: false,
        inputValue: '',
      },

      report: {
        report: null,
        isLoadingReport: false,
        vision: null,
        overlay: null,
      },

      activeTab: 'inspector',

      // ── Session actions ───────────────────────────────────────────────────

      startSession: () =>
        set((state) => ({
          session: {
            id: `session_${Date.now()}`,
            status: 'uploading',
            uploadedFiles: Object.values(state.upload.files).flat(),
            processingSteps: DEFAULT_PROCESSING_STEPS,
            defects: [],
            startedAt: new Date().toISOString(),
          },
          status: 'uploading',
        })),

      resetSession: () =>
        set({
          session: null,
          status: 'idle',
          upload: {
            files: { ...EMPTY_FILES },
            dragOver: { ...EMPTY_DRAG },
          },
          report: { report: null, isLoadingReport: false, vision: null, overlay: null },
        }),

      setStatus: (status) => set({ status }),

      startAppointmentSession: (sessionId) =>
        set((state) => ({
          session: {
            id: sessionId,
            mode: 'appointment',
            status: 'idle',
            uploadedFiles: [],
            processingSteps: [],
            defects: [],
            startedAt: new Date().toISOString(),
          },
          status: 'idle',
          report: { report: null, isLoadingReport: false, vision: null, overlay: null },
          chat: { ...state.chat, messages: [], inputValue: '' },
        })),

      setSessionId: (sessionId) =>
        set((state) => ({
          session: state.session ? { ...state.session, id: sessionId } : state.session,
        })),

      setVehicle: (vehicle) => set({ vehicle }),

      // ── Upload actions ───────────────────────────────────────────────────

      // Only one detection flow may hold files per inspection: surface OR
      // tyres, never both. Enforced here as well as in useFileUpload so the
      // invariant cannot be bypassed by a caller that skips the hook.
      addFile: (model, file) =>
        set((state) => {
          const otherOccupied = (Object.keys(state.upload.files) as DetectionModel[]).some(
            (m) => m !== model && state.upload.files[m].length > 0,
          )
          if (otherOccupied) return state

          // Cap reached — drop silently; useFileUpload explains it in the UI.
          if (state.upload.files[model].length >= MAX_FILES_PER_MODEL[model]) return state

          return {
            upload: {
              ...state.upload,
              files: {
                ...state.upload.files,
                [model]: [...state.upload.files[model], file],
              },
            },
          }
        }),

      removeFile: (model, fileId) =>
        set((state) => ({
          upload: {
            ...state.upload,
            files: {
              ...state.upload.files,
              [model]: state.upload.files[model].filter((f) => f.id !== fileId),
            },
          },
        })),

      setDragOver: (model, isDragging) =>
        set((state) => ({
          upload: {
            ...state.upload,
            dragOver: { ...state.upload.dragOver, [model]: isDragging },
          },
        })),

      clearFiles: (model) =>
        set((state) => ({
          upload: {
            ...state.upload,
            files: { ...state.upload.files, [model]: [] },
          },
        })),

      // ── Processing step actions ───────────────────────────────────────────

      setProcessingSteps: (steps) =>
        set((state) => ({
          session: state.session ? { ...state.session, processingSteps: steps } : state.session,
        })),

      updateStep: (stepId, status) =>
        set((state) => {
          if (!state.session) return state
          return {
            session: {
              ...state.session,
              processingSteps: state.session.processingSteps.map((s) =>
                s.id === stepId
                  ? {
                      ...s,
                      status,
                      completedAt:
                        status === 'done'
                          ? new Date().toLocaleTimeString('es-MX', {
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : s.completedAt,
                    }
                  : s,
              ),
            },
          }
        }),

      // ── Chat actions ──────────────────────────────────────────────────────

      addMessage: (msg) =>
        set((state) => ({
          chat: {
            ...state.chat,
            messages: [...state.chat.messages, msg],
          },
        })),

      setAgentTyping: (typing) =>
        set((state) => ({
          chat: { ...state.chat, isAgentTyping: typing },
        })),

      setInputValue: (val) =>
        set((state) => ({
          chat: { ...state.chat, inputValue: val },
        })),

      clearMessages: () =>
        set((state) => ({
          chat: { ...state.chat, messages: [] },
        })),

      // ── Report / results actions ──────────────────────────────────────────

      setSummary: (summary) =>
        set((state) => ({
          session: state.session ? { ...state.session, summary } : state.session,
        })),

      setDefects: (defects) =>
        set((state) => ({
          session: state.session ? { ...state.session, defects } : state.session,
        })),

      setReport: (report) =>
        set((state) => ({
          report: { ...state.report, report },
        })),

      setLoadingReport: (loading) =>
        set((state) => ({
          report: { ...state.report, isLoadingReport: loading },
        })),

      setVision: (vision) =>
        set((state) => ({
          report: { ...state.report, vision },
        })),

      setOverlay: (overlay) =>
        set((state) => ({
          report: { ...state.report, overlay },
        })),

      // ── UI actions ────────────────────────────────────────────────────────

      setActiveTab: (tab) => set({ activeTab: tab }),
    }),
    { name: 'car-inspector-store' },
  ),
)
