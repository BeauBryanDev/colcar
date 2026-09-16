import React, { useMemo, useState } from 'react'
import { FiImage } from 'react-icons/fi'
import type { OverlayImage, OverlayResponse, OverlayShape, VehiclePart } from '@/types'
import { PART_DISPLAY, DEFECT_DISPLAY } from '@/types'

/**
 * The analysed photo with its segmentation masks drawn over it.
 *
 * Both the pixels and the shapes come from the backend:
 *   GET /inspections/{id}/images/{image_id}   the stored upload
 *   GET /inspections/{id}/overlay             polygons in original-pixel space
 *
 * Coordinates are in *original image* pixels and `OverlayImage` carries that
 * original width/height, so setting the SVG viewBox to those dimensions makes
 * the overlay resolution-independent — it registers at any rendered size with
 * no scaling arithmetic here. The <img> and <svg> letterbox identically
 * (`object-contain` + `xMidYMid meet`), which is what keeps the two layers
 * aligned when the photo's aspect ratio differs from the box.
 *
 * Tyre defects have `polygon: null` — that model is detection-only with no
 * prototype masks — so they fall back to their bounding box rather than being
 * dropped, which would silently hide a blowout risk.
 */

const SEVERITY_COLOR: Record<string, string> = {
  grave: '#cc1f1f',
  moderado: '#f97316',
  leve: '#1a3a6e',
}

const PART_COLOR = '#c99a00'

interface AnnotatedImageProps {
  overlay: OverlayResponse
  /**
   * Object URLs for the files this browser uploaded, keyed by original name.
   *
   * When present these win over `imageUrl`: the pixels are already in memory,
   * so the annotated view appears instantly instead of waiting on a re-download
   * of a photo the user just sent us. `imageUrl` remains the fallback for a
   * reload or a different device, where no object URL exists.
   */
  localPreviews?: Record<string, string>
  className?: string
}

/** Stored names are `{index}_{originalName}`; match a local file back to one. */
function localSrc(filename: string, previews?: Record<string, string>): string | undefined {
  if (!previews) return undefined
  if (previews[filename]) return previews[filename]
  const hit = Object.keys(previews).find(
    (name) => filename === name || filename.endsWith(`_${name}`),
  )
  return hit ? previews[hit] : undefined
}

function points(poly: number[][]): string {
  return poly.map(([x, y]) => `${x},${y}`).join(' ')
}

function shapeLabel(s: OverlayShape): string {
  const name = DEFECT_DISPLAY[s.className as keyof typeof DEFECT_DISPLAY] ?? s.className
  if (!s.matchedPartName) return name
  const part = PART_DISPLAY[s.matchedPartName as VehiclePart] ?? s.matchedPartName
  return `${name} · ${part}`
}

const ImageCanvas: React.FC<{
  image: OverlayImage
  showParts: boolean
  src: string
}> = ({ image, showParts, src }) => {
  const { width, height } = image
  // Stroke widths scale with the image so they read the same on a 4000px photo
  // and a 640px one.
  const unit = Math.max(width, height)

  const parts = image.shapes.filter((s) => s.kind === 'part')
  const defects = image.shapes.filter((s) => s.kind === 'defect')

  return (
    <div className="relative w-full aspect-[4/3] rounded-xl overflow-hidden bg-brand-navy border-2 border-brand-blue">
      <img
        src={src}
        alt={`Imagen analizada: ${image.filename}`}
        className="absolute inset-0 w-full h-full object-contain"
      />

      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 w-full h-full"
        aria-hidden="true"
      >
        {/* Parts first, underneath: context, not findings */}
        {showParts &&
          parts.map((p) =>
            p.polygon?.length ? (
              <polygon
                key={p.detectionId}
                points={points(p.polygon)}
                fill={PART_COLOR}
                fillOpacity={0.10}
                stroke={PART_COLOR}
                strokeWidth={unit * 0.002}
                strokeDasharray={unit * 0.008}
              />
            ) : null,
          )}

        {/* Defects on top, coloured by severity */}
        {defects.map((d) => {
          const color = SEVERITY_COLOR[d.severidad ?? 'grave'] ?? '#cc1f1f'
          const [x1, y1, x2, y2] = d.bbox

          return (
            <g key={d.detectionId}>
              {d.polygon?.length ? (
                <polygon
                  points={points(d.polygon)}
                  fill={color}
                  fillOpacity={0.35}
                  stroke={color}
                  strokeWidth={unit * 0.004}
                />
              ) : (
                <rect
                  x={x1}
                  y={y1}
                  width={Math.max(x2 - x1, 0)}
                  height={Math.max(y2 - y1, 0)}
                  fill={color}
                  fillOpacity={0.18}
                  stroke={color}
                  strokeWidth={unit * 0.004}
                />
              )}

              {/* Outlined text stays legible over any photo */}
              <text
                x={x1}
                y={Math.max(y1 - unit * 0.008, unit * 0.03)}
                fill="#ffffff"
                stroke="#0a1628"
                strokeWidth={unit * 0.004}
                paintOrder="stroke"
                fontSize={unit * 0.026}
                fontWeight="700"
              >
                {shapeLabel(d)}
              </text>
            </g>
          )
        })}
      </svg>

      <div className="absolute top-2 right-2 bg-brand-navy/85 rounded-lg px-2 py-1">
        <span className="text-brand-yellow text-sm font-bold">
          {defects.length} defecto{defects.length !== 1 ? 's' : ''}
        </span>
      </div>
    </div>
  )
}

export const AnnotatedImage: React.FC<AnnotatedImageProps> = ({
  overlay,
  localPreviews,
  className = '',
}) => {
  const [index, setIndex] = useState(0)
  const [showParts, setShowParts] = useState(true)

  const images = useMemo(() => overlay.images ?? [], [overlay.images])
  const current = images[Math.min(index, Math.max(images.length - 1, 0))]

  if (!current) {
    return (
      <div
        className={`w-full aspect-[4/3] rounded-xl bg-brand-navy/10 border border-brand-navy/20 flex flex-col items-center justify-center gap-1 ${className}`}
      >
        <FiImage className="w-8 h-8 text-brand-navy/30" aria-hidden="true" />
        <span className="text-sm text-brand-navy">Sin imágenes analizadas</span>
      </div>
    )
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <ImageCanvas
        image={current}
        showParts={showParts}
        src={localSrc(current.filename, localPreviews) ?? current.imageUrl}
      />

      <div className="flex items-center justify-between gap-2 flex-wrap">
        {images.length > 1 && (
          <div className="flex items-center gap-1 flex-wrap">
            {images.map((img, i) => (
              <button
                key={img.imageId}
                type="button"
                onClick={() => setIndex(i)}
                className={[
                  'px-2 py-0.5 rounded text-sm font-bold border transition-colors',
                  i === index
                    ? 'bg-brand-navy text-brand-yellow border-brand-navy'
                    : 'bg-transparent text-brand-navy border-brand-navy/30 hover:bg-brand-navy/10',
                ].join(' ')}
              >
                {img.role === 'tire' ? 'Llanta' : `Img ${i + 1}`}
              </button>
            ))}
          </div>
        )}

        <label className="flex items-center gap-1.5 text-sm text-brand-navy font-semibold cursor-pointer">
          <input
            type="checkbox"
            checked={showParts}
            onChange={(e) => setShowParts(e.target.checked)}
            className="accent-brand-blue"
          />
          Mostrar piezas
        </label>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {(['grave', 'moderado', 'leve'] as const).map((sev) => (
          <span key={sev} className="flex items-center gap-1.5 text-sm text-brand-navy">
            <span
              className="w-3 h-3 rounded-sm border border-brand-navy/30"
              style={{ backgroundColor: SEVERITY_COLOR[sev] }}
            />
            {sev === 'grave' ? 'Grave' : sev === 'moderado' ? 'Medio' : 'Bajo'}
          </span>
        ))}
      </div>
    </div>
  )
}

export default AnnotatedImage
