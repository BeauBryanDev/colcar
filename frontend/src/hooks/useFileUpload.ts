import { useCallback, useState } from 'react'
import { useInspectionStore, MAX_FILES_PER_MODEL } from '@/stores/inspectionStore'
import type { DetectionModel, UploadedFile } from '@/types'

/**
 * Mirrors `settings.allowed_image_types` in app/core/config.py.
 *
 * Images only: the vision pipeline decodes still frames, and the backend
 * rejects video outright ("Formato no soportado. Usa JPG, PNG o WEBP."). The
 * UI used to offer MP4/MOV, so a user could pick a video, watch it land in the
 * panel, and only be refused after pressing Analizar.
 */
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_FILE_SIZE_MB = 200
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

/** Panel labels, for the "otro panel ya tiene archivos" message. */
const MODEL_LABEL: Record<DetectionModel, string> = {
  vehicle_parts: 'Vehículo y Partes',
  surface_defects: 'Defectos en Superficies',
  tires_wheels: 'Llantas y Ruedas',
}

export interface UseFileUploadReturn {
  files: UploadedFile[]
  isDragging: boolean
  /** False when another panel already holds files — only one flow runs at a time. */
  isLocked: boolean
  /** Why the panel is locked/rejecting, in Spanish. Null when fine. */
  error: string | null
  maxFiles: number
  addFiles: (rawFiles: FileList | File[]) => void
  removeFile: (fileId: string) => void
  clearFiles: () => void
  onDragEnter: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent) => void
}

export function useFileUpload(model: DetectionModel): UseFileUploadReturn {
  const files      = useInspectionStore((s) => s.upload.files[model])
  const allFiles   = useInspectionStore((s) => s.upload.files)
  const isDragging = useInspectionStore((s) => s.upload.dragOver[model])
  const addFileAction    = useInspectionStore((s) => s.addFile)
  const removeFileAction = useInspectionStore((s) => s.removeFile)
  const clearFilesAction = useInspectionStore((s) => s.clearFiles)
  const setDragOver      = useInspectionStore((s) => s.setDragOver)

  const [error, setError] = useState<string | null>(null)

  const maxFiles = MAX_FILES_PER_MODEL[model]

  // Only one detection flow may run per inspection: surface OR tyres, never both.
  const occupiedBy = (Object.keys(allFiles) as DetectionModel[]).find(
    (m) => m !== model && allFiles[m].length > 0,
  )
  const isLocked = occupiedBy !== undefined

  const addFiles = useCallback(
    (rawFiles: FileList | File[]) => {
      if (isLocked) {
        setError(
          `Solo puedes usar un panel a la vez. Vacía "${MODEL_LABEL[occupiedBy!]}" para usar este.`,
        )
        return
      }

      const arr = Array.from(rawFiles)
      let slots = maxFiles - files.length
      const problems: string[] = []

      for (const file of arr) {
        if (slots <= 0) {
          problems.push(
            `Máximo ${maxFiles} archivo${maxFiles !== 1 ? 's' : ''} en este panel.`,
          )
          break
        }
        if (!ACCEPTED_TYPES.includes(file.type)) {
          problems.push(`Formato no soportado (usa JPG, PNG o WEBP): ${file.name}`)
          continue
        }
        if (file.size > MAX_FILE_SIZE_BYTES) {
          problems.push(`Archivo demasiado grande (máx ${MAX_FILE_SIZE_MB}MB): ${file.name}`)
          continue
        }

        const uploadedFile: UploadedFile = {
          id: `${model}_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          name: file.name,
          size: file.size,
          type: file.type,
          model,
          preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
          uploadedAt: new Date().toISOString(),
          file,
        }
        addFileAction(model, uploadedFile)
        slots -= 1
      }

      setError(problems.length ? problems[0] : null)
    },
    [model, files.length, maxFiles, isLocked, occupiedBy, addFileAction],
  )

  const removeFile = useCallback(
    (fileId: string) => {
      const file = files.find((f) => f.id === fileId)
      if (file?.preview) URL.revokeObjectURL(file.preview)
      removeFileAction(model, fileId)
      setError(null)
    },
    [model, files, removeFileAction],
  )

  const clearFiles = useCallback(() => {
    files.forEach((f) => { if (f.preview) URL.revokeObjectURL(f.preview) })
    clearFilesAction(model)
    setError(null)
  }, [model, files, clearFilesAction])

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (!isLocked) setDragOver(model, true)
    },
    [model, setDragOver, isLocked],
  )

  const onDragLeave = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setDragOver(model, false)
    },
    [model, setDragOver],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setDragOver(model, false)
      if (e.dataTransfer.files?.length) {
        addFiles(e.dataTransfer.files)
      }
    },
    [model, setDragOver, addFiles],
  )

  return {
    files, isDragging, isLocked, error, maxFiles,
    addFiles, removeFile, clearFiles, onDragEnter, onDragLeave, onDrop,
  }
}
