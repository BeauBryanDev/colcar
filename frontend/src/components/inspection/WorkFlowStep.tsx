import React from 'react'
import { FiArrowRight } from 'react-icons/fi'

interface WorkFlowStepProps {
  number: number
  title: string
  subtitle: string
  icon: React.ReactNode
  isLast?: boolean
}

export const WorkFlowStep: React.FC<WorkFlowStepProps> = ({
  number,
  title,
  subtitle,
  icon,
  isLast = false,
}) => (
  <div className="flex items-center gap-3">
    {/* Step card */}
    <div className="flex flex-col items-center gap-1 min-w-[80px]">
      <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-white/10 border border-white/30">
        {icon}
      </div>
      <p className="text-white font-extrabold text-xs uppercase leading-tight text-center">
        {number}. {title}
      </p>
      <p className="text-white/70 text-xs text-center leading-tight">{subtitle}</p>
    </div>

    {/* Arrow separator */}
    {!isLast && (
      <FiArrowRight className="w-4 h-4 text-white/50 flex-shrink-0" aria-hidden="true" />
    )}
  </div>
)

export default WorkFlowStep
