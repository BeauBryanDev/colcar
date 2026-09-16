import React, { useRef } from 'react'
import { FiX, FiImage, FiFilm } from 'react-icons/fi'
import { UploadText } from './UploadText'
import type { UseFileUploadReturn } from '@/hooks/useFileUpload'
import type { UploadedFile } from '@/types'

interface UploadAreaProps extends Pick<
  UseFileUploadReturn,
  'files' | 'isDragging' | 'addFiles' | 'removeFile' | 'onDragEnter' | 'onDragLeave' | 'onDrop'
> {
  /** Another panel is in use — this one accepts nothing. */
  isLocked?: boolean
  /** Per-panel cap reached. */
  isFull?: boolean
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function FileItem({ file, onRemove }: { file: UploadedFile; onRemove: () => void }) {
  const isVideo = file.type.startsWith('video/')
  return (
    <li className="flex items-center gap-2 bg-brand-navy/10 rounded-md px-2 py-1.5 text-sm">
      {file.preview ? (
        <img src={file.preview} alt={file.name} className="w-8 h-8 object-cover rounded flex-shrink-0" />
      ) : isVideo ? (
        <FiFilm className="w-5 h-5 flex-shrink-0 text-brand-navy/60" />
      ) : (
        <FiImage className="w-5 h-5 flex-shrink-0 text-brand-navy/60" />
      )}
      <span className="flex-1 truncate font-medium text-brand-navy">{file.name}</span>
      <span className="text-brand-navy/50 flex-shrink-0">{formatBytes(file.size)}</span>
      <button
        type="button"
        aria-label={`Eliminar ${file.name}`}
        onClick={onRemove}
        className="flex-shrink-0 p-0.5 rounded hover:bg-brand-red/20 text-brand-navy/60 hover:text-brand-red transition-colors"
      >
        <FiX className="w-4 h-4" />
      </button>
    </li>
  )
}

/** The full drag-and-drop zone with file list preview */
export const UploadArea: React.FC<UploadAreaProps> = ({
  files,
  isDragging,
  addFiles,
  removeFile,
  onDragEnter,
  onDragLeave,
  onDrop,
  isLocked = false,
  isFull = false,
}) => {
  const inputRef = useRef<HTMLInputElement>(null)

  // A locked or full zone must not open the picker: the rejection would only
  // surface after the user had already chosen files.
  const isDisabled = isLocked || isFull

  const handleClick = () => {
    if (isDisabled) return
    inputRef.current?.click()
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      addFiles(e.target.files)
      e.target.value = ''
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".jpg,.jpeg,.png,.webp"
        className="hidden"
        onChange={handleChange}
        aria-label="Subir archivos"
      />

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={isDisabled ? -1 : 0}
        aria-label="Zona de carga de archivos"
        aria-disabled={isDisabled}
        onClick={handleClick}
        onKeyDown={(e) => e.key === 'Enter' && handleClick()}
        onDragEnter={onDragEnter}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={onDragLeave}
        onDrop={isDisabled ? (e) => e.preventDefault() : onDrop}
        className={[
          'rounded-lg transition-all duration-150',
          isDisabled ? 'cursor-not-allowed' : 'cursor-pointer',
        ].join(' ')}
      >
        <UploadText isDragging={isDragging} />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="flex flex-col gap-1 max-h-28 overflow-y-auto pr-1">
          {files.map((f) => (
            <FileItem key={f.id} file={f} onRemove={() => removeFile(f.id)} />
          ))}
        </ul>
      )}
    </div>
  )
}

export default UploadArea
