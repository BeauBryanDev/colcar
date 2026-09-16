import React, { useMemo, useState } from 'react'
import { SelectList } from '@/components/common/SelectList'
import {
  getBrands,
  getModelsForBrand,
  getYears,
  isModelOfBrand,
} from '@/services/catalogService'
import type { VehicleSelection } from '@/types/catalog'

interface VehicleSelectorProps {
  /** Fired on every change, with the full current selection. */
  onChange?: (selection: VehicleSelection) => void
  className?: string
}

/**
 * The three vehicle selects: brand → model → year.
 *
 * The model list is derived from the chosen brand, so it stays disabled until
 * a brand exists, and a model that does not belong to the newly chosen brand
 * is cleared rather than left behind (Renault Logan → Kia would otherwise
 * quote a Logan that Kia does not make).
 */
export const VehicleSelector: React.FC<VehicleSelectorProps> = ({
  onChange,
  className = '',
}) => {
  const [brand, setBrand] = useState<string>('')
  const [vehicleModel, setVehicleModel] = useState<string>('')
  const [year, setYear] = useState<string>('')

  const brands = useMemo(() => getBrands(), [])
  const years = useMemo(() => getYears(), [])
  const models = useMemo(() => getModelsForBrand(brand || null), [brand])

  const emit = (next: Partial<VehicleSelection>) => {
    onChange?.({
      brand: brand || null,
      vehicleModel: vehicleModel || null,
      year: year ? Number(year) : null,
      ...next,
    })
  }

  const handleBrandChange = (nextBrand: string) => {
    setBrand(nextBrand)

    // Keep the model only if the new brand actually offers it; otherwise clear.
    if (isModelOfBrand(nextBrand || null, vehicleModel || null)) {
      emit({ brand: nextBrand || null })
    } else {
      setVehicleModel('')
      emit({ brand: nextBrand || null, vehicleModel: null })
    }
  }

  const handleModelChange = (nextModel: string) => {
    setVehicleModel(nextModel)
    emit({ vehicleModel: nextModel || null })
  }

  const handleYearChange = (nextYear: string) => {
    setYear(nextYear)
    emit({ year: nextYear ? Number(nextYear) : null })
  }

  return (
    <div className={`grid grid-cols-1 sm:grid-cols-3 gap-3 ${className}`}>
      <SelectList
        label="Marca"
        value={brand}
        placeholder="Seleccionar marca…"
        options={brands.map((b) => ({ value: b.brand, label: b.brand }))}
        onChange={handleBrandChange}
      />

      <SelectList
        label="Modelo"
        value={vehicleModel}
        placeholder={brand ? 'Seleccionar modelo…' : '—'}
        options={models.map((m) => ({ value: m.name, label: m.name }))}
        onChange={handleModelChange}
        disabled={!brand}
        disabledHint="Elige una marca primero"
      />

      <SelectList
        label="Año"
        value={year}
        placeholder="Seleccionar año…"
        options={years.map((y) => ({ value: String(y), label: String(y) }))}
        onChange={handleYearChange}
      />
    </div>
  )
}

export default VehicleSelector
