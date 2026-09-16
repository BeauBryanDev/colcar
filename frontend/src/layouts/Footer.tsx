import React from 'react'
import {
  FiUploadCloud,
  FiEye,
  FiCode,
  FiCpu,
  FiDatabase,
  FiFileText,
} from 'react-icons/fi'
import { FiStar } from 'react-icons/fi'
import { WorkFlowStep } from '@/components/inspection/WorkFlowStep'

const STEPS = [
  {
    number: 1,
    title: 'SUBES ARCHIVOS',
    subtitle: 'Imagen / Video',
    icon: <FiUploadCloud className="w-7 h-7 text-white/80" />,
  },
  {
    number: 2,
    title: 'MODELOS DE VISIÓN',
    subtitle: '3 Modelos YOLO11m',
    icon: <FiEye className="w-7 h-7 text-white/80" />,
  },
  {
    number: 3,
    title: 'SALIDA JSON',
    subtitle: 'Estado del Vehículo',
    icon: <FiCode className="w-7 h-7 text-white/80" />,
  },
  {
    number: 4,
    title: 'CAR-LENS (LLM)',
    subtitle: 'Claude API',
    icon: <FiCpu className="w-7 h-7 text-white/80" />,
  },
  {
    number: 5,
    title: 'FUENTES EXTERNAS',
    subtitle: 'Parts API + RAG (RTM)',
    icon: <FiDatabase className="w-7 h-7 text-white/80" />,
  },
  {
    number: 6,
    title: 'INFORME DE INSPECCIÓN',
    subtitle: 'Costos, Cumplimiento, Recomendaciones',
    icon: <FiFileText className="w-7 h-7 text-white/80" />,
  },
]

export const Footer: React.FC = () => (
  <footer className="bg-brand-blue border-t-4 border-brand-red w-full">
    {/* Workflow section */}
    <div className="w-full px-6 lg:px-10 py-3 flex items-center justify-center gap-4 flex-wrap text-center">
      {/* Label */}
      <div className="flex-shrink-0">
        <p className="font-extrabold text-white text-sm uppercase tracking-wide leading-tight">
          ¿CÓMO FUNCIONA
          <br />
          CAR-LENS?
        </p>
      </div>

      {/* Step divider */}
      <span className="h-10 w-px bg-white/30" aria-hidden="true" />

      {/* Steps */}
      <div className="flex items-center gap-1 flex-wrap">
        {STEPS.map((step, idx) => (
          <WorkFlowStep
            key={step.number}
            number={step.number}
            title={step.title}
            subtitle={step.subtitle}
            icon={step.icon}
            isLast={idx === STEPS.length - 1}
          />
        ))}
      </div>
    </div>

    {/* Bottom tagline strip */}
    <div className="bg-brand-red py-1.5">
      <p className="text-center text-white font-display tracking-widest text-sm uppercase flex items-center justify-center gap-3">
        <FiStar className="w-4 h-4 fill-white" aria-hidden="true" />
        TECNOLOGÍA DE IA. RESULTADOS CONFIABLES.
        <FiStar className="w-4 h-4 fill-white" aria-hidden="true" />
      </p>
    </div>
  </footer>
)

export default Footer
