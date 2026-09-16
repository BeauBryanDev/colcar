import React from 'react'
import { FiUploadCloud } from 'react-icons/fi'

interface UploadTextProps {
  isDragging?: boolean
}

/** The dashed inner drop-target with the upload icon and text */
export const UploadText: React.FC<UploadTextProps> = ({ isDragging = false }) => (
  <div
    className={[
      'flex flex-col items-center justify-center gap-1 py-5 px-3',
      'border-2 border-dashed rounded-lg pointer-events-none select-none',
      'transition-colors duration-150',
      isDragging
        ? 'border-brand-blue bg-brand-blue/10 text-brand-navy'
        : 'border-brand-blue/40 bg-transparent text-brand-navy',
    ].join(' ')}
  >
    <FiUploadCloud className="w-9 h-9 opacity-80" />
    <p className="text-base font-bold text-center leading-tight">
      ARRASTRAR Y SOLTAR
    </p>
    <p className="text-sm text-center opacity-75 leading-snug">
      o haz clic para subir
      <br />
      Imagen / Video
    </p>
  </div>
)

export default UploadText
