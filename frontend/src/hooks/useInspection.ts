import { useCallback, useRef } from 'react'
import { useInspectionStore } from '@/stores/inspectionStore'
import { inspectionService } from '@/services/inspectionService'
import { reportService } from '@/services/reportService'
import type { ChatMessage, DetectionModel, UploadedFile } from '@/types'

// /status is a cheap in-memory read, so polling faster costs the backend
// almost nothing and cuts up to 2s of dead time off the perceived wait: the
// run finishes between polls and the SPA only notices on the next tick.
const POLL_INTERVAL_MS = 800

export function useInspection() {
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const {
    session,
    status,
    upload,
    vehicle,
    chat,
    report,
    startSession: storeStart,
    setStatus,
    addMessage,
    setAgentTyping,
    setInputValue,
    setReport,
    setLoadingReport,
    setVision,
    setOverlay,
    setProcessingSteps,
    setSessionId,
    resetSession,
    startAppointmentSession,
  } = useInspectionStore()

  /** Total file count across all models */
  const totalFiles = Object.values(upload.files).reduce((sum, arr) => sum + arr.length, 0)

  /** Which panel is in use. Only one flow runs per inspection. */
  const activeModel = (Object.keys(upload.files) as DetectionModel[]).find(
    (m) => upload.files[m].length > 0,
  )

  const isBusy = status === 'uploading' || status === 'processing' || status === 'analyzing'
  const canSubmit = totalFiles > 0 && !isBusy

  /** Start inspection: create session → upload files → run → poll */
  const startInspection = useCallback(async () => {
    if (!canSubmit) return

    try {
      storeStart()
      setStatus('uploading')

      // 1. Create session
      const { sessionId } = await inspectionService.startSession(vehicle)
      // The store seeded a placeholder id; every later call (chat, status,
      // results) must use the backend's real one.
      setSessionId(sessionId)

      // 2. Upload files per model, carrying the real File handles kept by
      //    useFileUpload. The vehicle selection rides along on every call —
      //    the backend reads it from the first upload that supplies it.
      for (const [model, files] of Object.entries(upload.files) as [
        DetectionModel,
        UploadedFile[],
      ][]) {
        if (files.length === 0) continue
        await inspectionService.uploadFiles(
          sessionId,
          model,
          files.map((f) => f.file),
          vehicle,
        )
      }

      // 3. Kick off inference
      setStatus('processing')
      await inspectionService.runInspection(sessionId)

      // 4. Poll status
      //
      // Vision finishes in ~1.1s but the agent takes ~16s, so waiting for
      // `complete` leaves the user staring at a spinner for 15s with the
      // detections already sitting on the server. The backend flips to
      // `analyzing` the moment vision is done, which is the cue to render the
      // masks; the diagnosis and quote fill in when the agent lands.
      let visionShown = false

      pollingRef.current = setInterval(async () => {
        const { steps, overallStatus } = await inspectionService.getProcessingStatus(sessionId)
        // Replace wholesale: the backend owns the step list, its ids and labels.
        if (steps.length) setProcessingSteps(steps)

        if (overallStatus === 'analyzing' && !visionShown) {
          visionShown = true
          setStatus('analyzing')
          try {
            const [results, overlayData] = await Promise.all([
              reportService.getResults(sessionId),
              inspectionService.getOverlay(sessionId),
            ])
            if (results.vision) setVision(results.vision)
            setOverlay(overlayData)
          } catch (err) {
            // Non-fatal: the final fetch on `complete` will retry.
            console.warn('Early vision fetch failed; will retry on completion', err)
          }
        }

        if (overallStatus === 'complete' || overallStatus === 'error') {
          if (pollingRef.current) clearInterval(pollingRef.current)
          setStatus(overallStatus)

          if (overallStatus === 'complete') {
            setLoadingReport(true)
            try {
              // In parallel: these are independent reads, and running them in
              // series added a whole round trip to the visible wait.
              const [results, overlayData] = await Promise.all([
                reportService.getResults(sessionId),
                inspectionService.getOverlay(sessionId),
              ])
              setReport(results.report)
              if (results.vision) setVision(results.vision)
              setOverlay(overlayData)
            } finally {
              setLoadingReport(false)
            }
          }
        }
      }, POLL_INTERVAL_MS)
    } catch (err) {
      setStatus('error')
      if (pollingRef.current) clearInterval(pollingRef.current)
      console.error('Inspection error:', err)
    }
  }, [
    canSubmit, upload.files, vehicle, storeStart, setStatus, setProcessingSteps,
    setLoadingReport, setReport, setVision, setOverlay, setSessionId,
  ])

  /** Send a chat message to Car-Lens */
  const sendMessage = useCallback(async () => {
    const text = chat.inputValue.trim()
    if (!text || !session?.id) return

    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }),
    }
    addMessage(userMsg)
    setInputValue('')
    setAgentTyping(true)

    try {
      const { reply, timestamp } = await inspectionService.sendChatMessage(session.id, text)
      const agentMsg: ChatMessage = {
        id: `agent_${Date.now()}`,
        role: 'agent',
        content: reply,
        timestamp,
      }
      addMessage(agentMsg)
    } catch (err) {
      // api.ts already unwrapped `{detail}` into Error.message, and the backend
      // writes those in Spanish — show it rather than a generic fallback.
      const detail = err instanceof Error && err.message ? err.message : null
      addMessage({
        id: `err_${Date.now()}`,
        role: 'agent',
        content:
          detail ?? 'Lo siento, ocurrió un error al procesar tu mensaje. Por favor intenta de nuevo.',
        timestamp: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }),
      })
    } finally {
      setAgentTyping(false)
    }
  }, [chat.inputValue, session, addMessage, setInputValue, setAgentTyping])

  /** Trigger agent actions (cost estimate, compliance, explain defects) */
  const triggerAction = useCallback(
    async (action: 'estimate_costs' | 'verify_compliance' | 'explain_defects') => {
      if (!session?.id) return
      setAgentTyping(true)

      try {
        const { reply, timestamp } = await inspectionService.triggerAction(session.id, action)
        addMessage({ id: `action_${Date.now()}`, role: 'agent', content: reply, timestamp })
      } catch (err) {
        const detail = err instanceof Error && err.message ? err.message : null
        addMessage({
          id: `err_${Date.now()}`,
          role: 'agent',
          content: detail ?? 'Error al procesar la acción. Por favor intenta de nuevo.',
          timestamp: new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }),
        })
      } finally {
        setAgentTyping(false)
      }
    },
    [session, addMessage, setAgentTyping],
  )

  /** "Cambiar Cita": chat with the agent about an existing booking, no photos. */
  const startAppointmentChat = useCallback(async () => {
    if (pollingRef.current) clearInterval(pollingRef.current)
    const now = () => new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
    setAgentTyping(true)

    try {
      const { sessionId } = await inspectionService.startAppointmentChat()
      startAppointmentSession(sessionId)
      // Local greeting: no Claude call is spent just to say hello.
      addMessage({
        id: `agent_${Date.now()}`,
        role: 'agent',
        content:
          'Hola, soy Colcar. Con gusto te ayudo con tu cita. Para encontrarla necesito ' +
          'el **código de la cita**, tu **correo** y la **placa** del vehículo.',
        timestamp: now(),
      })
    } catch (err) {
      const detail = err instanceof Error && err.message ? err.message : null
      addMessage({
        id: `err_${Date.now()}`,
        role: 'agent',
        content: detail ?? 'No se pudo iniciar la conversación sobre tu cita. Intenta de nuevo.',
        timestamp: now(),
      })
    } finally {
      setAgentTyping(false)
    }
  }, [startAppointmentSession, addMessage, setAgentTyping])

  const reset = useCallback(() => {
    if (pollingRef.current) clearInterval(pollingRef.current)
    resetSession()
  }, [resetSession])

  return {
    session,
    status,
    totalFiles,
    activeModel,
    canSubmit,
    isBusy,
    vehicle,
    chat,
    report,
    startInspection,
    sendMessage,
    triggerAction,
    startAppointmentChat,
    reset,
  }
}
