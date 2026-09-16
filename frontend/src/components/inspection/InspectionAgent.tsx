import React, { useRef, useEffect } from 'react'
import { FiSend, FiStar } from 'react-icons/fi'
import { Badge } from '@/components/common/Badge'
import { ChatMessage } from './ChatMessage'
import { BubbleChat } from './BubbleChat'
import { ProcessingStatus } from './ProcessingStatus'
import { InspectionActions } from './InspectionActions'
import { useInspectionStore } from '@/stores/inspectionStore'
import { useInspection } from '@/hooks/useInspection'
import chatIconUrl from '@/assets/chat_icon.svg'

interface InspectionAgentProps {
  onEstimateCosts: () => void
  onVerifyCompliance: () => void
  onExplainDefects: () => void
  onChangeAppointment: () => void
}

export const InspectionAgent: React.FC<InspectionAgentProps> = ({
  onEstimateCosts,
  onVerifyCompliance,
  onExplainDefects,
  onChangeAppointment,
}) => {
  const messages      = useInspectionStore((s) => s.chat.messages)
  const isTyping      = useInspectionStore((s) => s.chat.isAgentTyping)
  const inputValue    = useInspectionStore((s) => s.chat.inputValue)
  const session       = useInspectionStore((s) => s.session)
  const setInputValue = useInspectionStore((s) => s.setInputValue)

  // POST /api/inspections/chat — continues the same agent thread.
  const { sendMessage, isBusy } = useInspection()

  const scrollRef = useRef<HTMLDivElement>(null)

  // Scroll the message list itself rather than calling scrollIntoView, which
  // walks up and can drag the whole page now that this region has its own
  // scrollbar.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, isTyping])

  const processingSteps = session?.processingSteps ?? []
  const showProcessing =
    session &&
    ['processing', 'analyzing'].includes(session.status) &&
    processingSteps.length > 0

  const hasSession = Boolean(session?.id)
  const actionsDisabled = !hasSession || isTyping
  const appointmentMode = session?.mode === 'appointment'

  const handleSend = () => {
    if (!inputValue.trim() || actionsDisabled) return
    void sendMessage()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="bg-brand-navy rounded-2xl border-2 border-brand-blue flex flex-col h-full min-h-0 overflow-hidden">

      {/*   Agent header   */}
      <div className="flex-shrink-0 flex items-center gap-4 px-5 py-4 border-b border-white/10">
        {/* Avatar */}
        <div className="flex-shrink-0 w-14 h-14 rounded-full bg-brand-blue border-2 border-brand-yellow overflow-hidden">
          <img src={chatIconUrl} alt="Car-Lens" className="w-full h-full object-cover" />
        </div>

        {/* Name + tagline */}
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <FiStar className="w-5 h-5 text-brand-yellow fill-brand-yellow" aria-hidden="true" />
            <h2 className="font-display text-brand-yellow text-3xl tracking-widest uppercase">
              COLCAR 
            </h2>
            <FiStar className="w-5 h-5 text-brand-yellow fill-brand-yellow" aria-hidden="true" />
            <Badge variant="green" dot>EN LÍNEA</Badge>
          </div>
          <p className="text-brand-yellow/80 text-sm font-semibold uppercase tracking-wider mt-0.5">
            Agente de Inspección con IA
          </p>
        </div>
      </div>

      {/* Sub-header description  */}
      {/* Hidden below sm: on a phone this blurb eats the height the message
          list needs and overlaps the agent's first reply. It is a description
          of the product, not part of the conversation, so dropping it there
          costs nothing. */}
      <div className="hidden sm:block flex-shrink-0 px-5 py-3 border-b border-white/10 
      bg-brand-blue/20">
        <p className="text-white/80 text-base leading-relaxed">
          Analizo tu vehículo usando modelos de Visión por IA y razonamiento LLM
          para ofrecerte una inspección precisa, estimación de costos y guía legal.
        </p>
      </div>

      {/*   Chat messages area   */}
      {/* Only this region scrolls. `min-h-0` is load-bearing: without it a
          flex child refuses to shrink below its content, so the list grows the
          page instead of overflowing into its own scrollbar. */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto px-5 py-5 flex flex-col gap-5"
        aria-label="Conversación con Car-Lens"
        aria-live="polite"
      >
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {showProcessing && (
          <ProcessingStatus
            steps={processingSteps}
            timestamp={new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
          />
        )}

        {isTyping && <BubbleChat />}
      </div>

      {/*   Input bar  */}
      <div className="flex-shrink-0 px-5 py-4 border-t border-white/10 flex flex-col gap-3">
        {/* Text input + send */}
        <div className="flex items-center gap-3 bg-brand-blue/30 rounded-xl border border-white/20 px-4 py-3">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={actionsDisabled}
            maxLength={4000}
            placeholder={
              appointmentMode
                ? 'Escribe el código de tu cita, tu correo y la placa...'
                : hasSession
                ? 'Pregunta a Car-Lens sobre tu inspección...'
                : 'Sube imágenes y pulsa Analizar para iniciar la conversación'
            }
            className="flex-1 bg-transparent text-white placeholder-white/50 text-base outline-none disabled:cursor-not-allowed"
            aria-label="Mensaje a Car-Lens"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!inputValue.trim() || actionsDisabled}
            className={[
              'flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center transition-all',
              inputValue.trim() && !actionsDisabled
                ? 'bg-brand-red hover:bg-red-600 text-white'
                : 'bg-white/10 text-white/30 cursor-not-allowed',
            ].join(' ')}
            aria-label="Enviar mensaje"
          >
            <FiSend className="w-5 h-5" />
          </button>
        </div>

        {/* Quick action buttons */}
        <InspectionActions
          onEstimateCosts={onEstimateCosts}
          onVerifyCompliance={onVerifyCompliance}
          onExplainDefects={onExplainDefects}
          disabled={actionsDisabled || appointmentMode}
          onChangeAppointment={onChangeAppointment}
          changeAppointmentDisabled={isTyping || isBusy}
        />

        {/* Footer note */}
        <p className="text-white/40 text-xs text-center leading-snug">
          Car-Lens se conecta con Claude (LLM), catálogo de precios y RAG — Ministerio de Transporte.
        </p>
      </div>
    </div>
  )
}

export default InspectionAgent
