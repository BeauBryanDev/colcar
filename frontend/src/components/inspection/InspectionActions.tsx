import React from 'react'
import { FiDollarSign, FiShield, FiInfo, FiCalendar } from 'react-icons/fi'
import { Button } from '@/components/common/Button'

interface InspectionActionsProps {
  onEstimateCosts: () => void
  onVerifyCompliance: () => void
  onExplainDefects: () => void
  // Rescheduling does not depend on an inspection, so it is not gated by
  // `disabled`. Omitted handler -> the button renders disabled.
  onChangeAppointment?: () => void
  changeAppointmentDisabled?: boolean
  disabled?: boolean
}

export const InspectionActions: React.FC<InspectionActionsProps> = ({
  onEstimateCosts,
  onVerifyCompliance,
  onExplainDefects,
  onChangeAppointment,
  changeAppointmentDisabled = false,
  disabled = false,
}) => (
  <div className="flex flex-wrap gap-2">
    <Button
      variant="yellow"
      size="md"
      icon={<FiDollarSign className="w-4 h-4" />}
      onClick={onEstimateCosts}
      disabled={disabled}
      title="Estimar Costos de Reparación"
    >
      <span className="truncate">Estimar Costos de Reparación</span>
    </Button>

    <Button
      variant="ghost"
      size="md"
      icon={<FiShield className="w-4 h-4" />}
      onClick={onVerifyCompliance}
      disabled={disabled}
      title="Verificar Cumplimiento Legal"
    >
      <span className="truncate">Verificar Cumplimiento Legal</span>
    </Button>

    <Button
      variant="ghost"
      size="md"
      icon={<FiInfo className="w-4 h-4" />}
      onClick={onExplainDefects}
      disabled={disabled}
      title="Explicar Defectos"
    >
      <span className="truncate">Explicar Defectos</span>
    </Button>

    <Button
      variant="secondary"
      size="md"
      icon={<FiCalendar className="w-4 h-4" />}
      onClick={onChangeAppointment}
      disabled={!onChangeAppointment || changeAppointmentDisabled}
      title="Cambiar Cita"
    >
      <span className="truncate">Cambiar Cita</span>
    </Button>
  </div>
)

export default InspectionActions
