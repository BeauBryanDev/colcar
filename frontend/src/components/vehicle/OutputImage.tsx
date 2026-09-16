import React from 'react'
import carIconUrl from '@/assets/car_icon.svg'

interface OutputImageProps {
  /** Annotated image URL returned by the backend after YOLO processing */
  imageUrl?: string
}

// Matches SeveridadDisplay in app/schemas/common.py: Grave / Medio / Bajo.
const LEGEND = [
  { label: 'Grave', color: 'bg-brand-red' },
  { label: 'Medio', color: 'bg-orange-400' },
  { label: 'Bajo',  color: 'bg-brand-blue' },
]

export const OutputImage: React.FC<OutputImageProps> = ({ imageUrl }) => (
  <div className="flex flex-col gap-2">
    {/* Image or placeholder */}
    <div className="relative w-full aspect-[4/3] rounded-xl overflow-hidden bg-brand-navy/10 border border-brand-navy/20 flex items-center justify-center">
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Vehículo inspeccionado con anotaciones de defectos"
          className="w-full h-full object-contain"
        />
      ) : (
        <img
          src={carIconUrl}
          alt="Vista superior del vehículo"
          className="w-64 h-64 object-contain opacity-40"
          aria-label="Imagen del vehículo no disponible"
        />
      )}
    </div>

    {/* Severity legend */}
    <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Leyenda de severidad">
      {LEGEND.map((item) => (
        <li key={item.label} className="flex items-center gap-1 text-sm text-brand-navy font-semibold">
          <span className={`w-3 h-3 rounded-sm ${item.color}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  </div>
)

export default OutputImage
