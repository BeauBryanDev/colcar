import React from 'react'
import { FiShield, FiAlertCircle, FiDisc } from 'react-icons/fi'
import { Badge } from '@/components/common/Badge'
import { UploadArea } from './UploadArea'
import { useFileUpload } from '@/hooks/useFileUpload'
import type { DetectionModel } from '@/types'

// Panel config  — title, subtitle, icon, border color, icon background

interface PanelConfig {
  title: string
  subtitle: string
  Icon: React.ElementType
  borderColor: string
  iconBg: string
}

const PANEL_CONFIG: Record<DetectionModel, PanelConfig> = {
  vehicle_parts: {
    title: 'DETECCIÓN DE VEHÍCULO Y PARTES',
    subtitle: 'Detecta el vehículo y segmentos de sus partes',
    Icon: FiShield,
    borderColor: 'border-brand-blue',
    iconBg: 'bg-brand-blue',
  },
  surface_defects: {
    title: 'DETECCIÓN DE DEFECTOS EN SUPERFICIES',
    subtitle: 'Detecta defectos y segmentos en superficies',
    Icon: FiAlertCircle,
    borderColor: 'border-brand-red',
    iconBg: 'bg-brand-red',
  },
  tires_wheels: {
    title: 'DETECCIÓN DE LLANTAS Y RUEDAS',
    subtitle: 'Detecta defectos en llantas y ruedas',
    Icon: FiDisc,
    borderColor: 'border-brand-blue',
    iconBg: 'bg-brand-blue',
  },
}

// ─── Component ────────────────────────────────────────────────────────────────

interface UploadPanelProps {
  model: DetectionModel
}

export const UploadPanel: React.FC<UploadPanelProps> = ({ model }) => {
  const config = PANEL_CONFIG[model]
  const upload = useFileUpload(model)
  const { Icon } = config

  return (
    <div
      className={[
        'bg-brand-yellow rounded-xl border-2 p-3 flex flex-col gap-3 transition-opacity',
        config.borderColor,
        upload.isLocked ? 'opacity-50' : '',
      ].join(' ')}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        {/* Icon bubble */}
        <div
          className={[
            'flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center',
            config.iconBg,
          ].join(' ')}
          aria-hidden="true"
        >
          <Icon className="w-5 h-5 text-white" />
        </div>

        {/* Title + badge */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-brand-navy font-extrabold text-sm leading-tight uppercase tracking-wide">
              {config.title}
            </span>
            <Badge variant="navy">YOLO11m</Badge>
          </div>
          <p className="text-brand-navy/80 text-sm mt-0.5 leading-snug">{config.subtitle}</p>
        </div>
      </div>

      {/* Drop zone */}
      <UploadArea
        files={upload.files}
        isDragging={upload.isDragging}
        addFiles={upload.addFiles}
        removeFile={upload.removeFile}
        onDragEnter={upload.onDragEnter}
        onDragLeave={upload.onDragLeave}
        onDrop={upload.onDrop}
        isLocked={upload.isLocked}
        isFull={upload.files.length >= upload.maxFiles}
      />

      {/* Rejection reason — wrong type, too big, cap reached, or panel locked */}
      {upload.error && (
        <p className="text-sm text-brand-red font-semibold leading-snug">{upload.error}</p>
      )}

      {/* File count / cap */}
      <p className="text-sm text-brand-navy/70 text-right">
        {upload.files.length} / {upload.maxFiles} archivo
        {upload.maxFiles !== 1 ? 's' : ''}
      </p>
    </div>
  )
}

export default UploadPanel
