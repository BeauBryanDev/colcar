import React, { useMemo } from 'react'
import { FiChevronRight, FiFileText } from 'react-icons/fi'
import { UploadPanel } from '@/components/upload/UploadPanel'
import { InspectionAgent } from '@/components/inspection/InspectionAgent'
import { InspectionMetrics } from '@/components/vehicle/InspectionMetrics'
import { DefectsByType } from '@/components/vehicle/DefectsByType'
import { OutputImage } from '@/components/vehicle/OutputImage'
import { VehicleSelector } from '@/components/vehicle/VehicleSelector'
import { ScannerAnimation } from '@/components/vehicle/ScannerAnimation'
import { AnnotatedImage } from '@/components/vehicle/AnnotatedImage'
import { DetectedParts } from '@/components/vehicle/DetectedParts'
import { SubmitAnalysis } from '@/components/upload/SubmitAnalysis'
import { Button } from '@/components/common/Button'
import { useInspection } from '@/hooks/useInspection'
import { useInspectionStore } from '@/stores/inspectionStore'
import { deriveDefectsByType, deriveVehicleSummary } from '@/services/summaryService'
import type { DefectSummary } from '@/types'

// COMPONENTS

export const Sections: React.FC = () => {
  const { triggerAction, startAppointmentChat, isBusy } = useInspection()
  const uploadFiles = useInspectionStore((s) => s.upload.files)

  // Object URLs for the files this browser uploaded, keyed by original name.
  // Reused by the annotated view so the analysed photo does not have to be
  // downloaded back from the server.
  const localPreviews = useMemo(() => {
    const map: Record<string, string> = {}
    for (const f of Object.values(uploadFiles).flat()) {
      if (f.preview) map[f.name] = f.preview
    }
    return map
  }, [uploadFiles])

  // Preview of whatever is being analysed, for the scanner overlay.
  const scanningPreview = Object.values(uploadFiles).flat().find((f) => f.preview)?.preview

  const session = useInspectionStore((s) => s.session)
  const overlay = useInspectionStore((s) => s.report.overlay)
  const vision  = useInspectionStore((s) => s.report.vision)
  const report  = useInspectionStore((s) => s.report.report)

  // Label of the stage currently running, straight from the /status poll.
  const runningStep = session?.processingSteps.find((st) => st.status === 'running')

  // Everything below is derived from the real payloads — no mock fallbacks.
  const defectsByType: DefectSummary[] = useMemo(() => deriveDefectsByType(vision), [vision])
  const summary = useMemo(() => deriveVehicleSummary(vision, report), [vision, report])

  // Kept on the store so the upload call can send it as brand / vehicle_model / year.
  const setVehicle = useInspectionStore((s) => s.setVehicle)

  return (
    <main className="flex-1 bg-brand-red/30 w-full flex flex-col">
      <div className="w-full px-6 lg:px-10 py-5 flex flex-col flex-1 gap-4">

        {/* ── Upload section title ────────────────────────────────────── */}
        <div className="flex items-center gap-2">
          <span className="text-brand-red font-extrabold text-lg">★</span>
          <h2 className="font-extrabold text-brand-navy uppercase text-base tracking-wide">
            1. SUBIR IMAGEN  
          </h2>
        </div>

        {/* ── 3-column grid — fills all remaining vertical space ──────── */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr_1fr] gap-5 flex-1 items-stretch">

          {/* ── LEFT: Upload panels ──────────────────────────────────── */}
          <div className="flex flex-col gap-4 min-w-0">
            {/* Vehicle identity — the brand sets the price index server-side */}
            <div className="bg-brand-yellow rounded-xl border-2 border-brand-gold p-3">
              <h3 className="font-extrabold text-brand-navy uppercase text-base tracking-wide mb-2">
                DATOS DEL VEHÍCULO
              </h3>
              <VehicleSelector onChange={setVehicle} />
            </div>

            <UploadPanel model="surface_defects" />
            <UploadPanel model="tires_wheels" />

            {/* Trigger: uploads the files and starts backend inference */}
            <SubmitAnalysis />

            {/* File format note */}
            <p className="text-brand-navy text-base text-center leading-snug px-2">
              Formatos soportados: JPG, PNG, WEBP
              <br />
              Tamaño máximo por archivo: 200MB
            </p>
            <p className="text-brand-navy text-base text-center leading-snug px-2">
              Por Favor Asegurse que  su foto incluya la pieza del auto donde el defecto 
              esta contenido en la imagen, asi nuestro sistema de vision artificial
              Puede detectar la parte dodne se encuentra el defecto y dar una mejor estimacion
              de precios de reparacion y pulido de su vehiculo.
            </p>
          </div>

          {/* ── CENTER: Car-Lens agent — bounded so the chat scrolls ──────
              The height cap is what gives the message list something to
              overflow inside. Without it the column grows with every message
              and the whole page gets taller instead. */}
          <div className="flex flex-col min-w-0 min-h-0 h-[75vh] lg:h-[calc(100vh-14rem)] lg:min-h-[32rem]">
            <InspectionAgent
              onEstimateCosts={() => void triggerAction('estimate_costs')}
              onVerifyCompliance={() => void triggerAction('verify_compliance')}
              onExplainDefects={() => void triggerAction('explain_defects')}
              onChangeAppointment={() => void startAppointmentChat()}
            />
          </div>

          {/* ── RIGHT: Vehicle summary / charts ───────────────────────── */}
          <div className="bg-brand-yellow rounded-2xl border-2 border-brand-gold flex flex-col gap-4 p-4 min-w-0">

            {/* Metrics row */}
            <InspectionMetrics summary={summary} />

            {/* Parts the vision model found, damaged ones first */}
            <DetectedParts vision={vision} />

            {/* Defects by type */}
            <div>
              <h3 className="font-extrabold text-brand-navy uppercase text-base tracking-wide mb-2">
                DEFECTOS POR TIPO
              </h3>
              <DefectsByType data={defectsByType} />
            </div>

            {/* Annotated output image — scanner overlay while work is in flight */}
            <div>
              <h3 className="font-extrabold text-brand-navy uppercase text-base tracking-wide mb-1">
                IMAGEN ANALIZADA
              </h3>
              {overlay ? (
                <AnnotatedImage overlay={overlay} localPreviews={localPreviews} />
              ) : isBusy ? (
                <ScannerAnimation
                  imageUrl={scanningPreview}
                  stageLabel={runningStep?.label}
                />
              ) : (
                <OutputImage imageUrl={undefined} />
              )}
            </div>

            {/* Ver Informe Detallado button */}
            <Button
              variant="yellow"
              size="sm"
              fullWidth
              icon={<FiFileText className="w-4 h-4" />}
              iconPosition="left"
              className="border-brand-gold border justify-between mt-auto"
            >
              <span className="flex-1 text-left font-bold text-brand-navy uppercase tracking-wide text-base">
                VER INFORME DETALLADO
              </span>
              <FiChevronRight className="w-4 h-4 text-brand-navy/60 flex-shrink-0" />
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}

export default Sections
