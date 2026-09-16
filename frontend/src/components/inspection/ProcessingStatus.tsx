import React from 'react'
import { FiCheckCircle, FiLoader, FiCircle, FiAlertCircle } from 'react-icons/fi'
import type { ProcessingStep } from '@/types'

interface ProcessingStatusProps {
  steps: ProcessingStep[]
  timestamp?: string
}

const StepIcon: React.FC<{ status: ProcessingStep['status'] }> = ({ status }) => {
  switch (status) {
    case 'done':
      return <FiCheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />
    case 'running':
      return <FiLoader className="w-4 h-4 text-brand-yellow flex-shrink-0 animate-spin" />
    case 'error':
      return <FiAlertCircle className="w-4 h-4 text-brand-red flex-shrink-0" />
    default:
      return <FiCircle className="w-4 h-4 text-white/30 flex-shrink-0" />
  }
}

export const ProcessingStatus: React.FC<ProcessingStatusProps> = ({ steps, timestamp }) => (
  <div className="flex items-start gap-2 max-w-[92%]">
    {/* Left side: plain agent bubble without avatar */}
    <div className="flex flex-col gap-0.5 flex-1">
      <div className="bg-white/95 rounded-2xl rounded-tl-sm px-3 py-3 shadow-sm flex flex-col gap-2">
        {steps.map((step) => (
          <div key={step.id} className="flex items-center gap-2">
            <StepIcon status={step.status} />
            <span
              className={[
                'text-sm leading-snug',
                step.status === 'done'
                  ? 'text-brand-navy font-medium'
                  : step.status === 'running'
                  ? 'text-brand-navy font-semibold'
                  : step.status === 'error'
                  ? 'text-brand-red font-medium'
                  : 'text-brand-navy/40',
              ].join(' ')}
            >
              {step.label}
              {step.status === 'running' ? '...' : step.status === 'done' ? ': Completado' : ''}
            </span>
          </div>
        ))}
      </div>
      {timestamp && (
        <span className="text-white/40 text-[10px] pl-1">{timestamp}</span>
      )}
    </div>
  </div>
)

export default ProcessingStatus
