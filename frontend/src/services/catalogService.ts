/**
 * Vehicle catalog lookups for the brand / model / year selects.
 *
 * Data currently comes from the bundled `src/data/carModels.json`, a copy of
 * the backend's `app/rag/car_models.json`. The backend also serves the same
 * catalog from `GET /api/vehicles/brands` (brands + models + years in one
 * call); switching to it means replacing the body of `getBrands()` / `getYears()`
 * here and nothing else — no component reads the JSON directly.
 */

import carModels from '@/data/carModels.json'
import type { CarBrand, CarModelOption } from '@/types/catalog'

/** Oldest model year offered — mirrors `_OLDEST_YEAR` in app/routers/vehicles.py. */
export const OLDEST_YEAR = 1990

/** Newest model year offered. Vehicles ship ahead of the calendar year. */
export const NEWEST_YEAR = 2027

const BRANDS = carModels as CarBrand[]

/** All brands, alphabetical. The JSON is ordered by price index, which is not a useful browse order. */
export function getBrands(): CarBrand[] {
  return [...BRANDS].sort((a, b) => a.brand.localeCompare(b.brand))
}

/** Look up a single brand row. Returns undefined for an unknown/empty brand. */
export function findBrand(brand: string | null): CarBrand | undefined {
  if (!brand) return undefined
  return BRANDS.find((b) => b.brand === brand)
}

/**
 * Models belonging to `brand`, alphabetical. Empty when no brand is chosen yet —
 * this is what drives the model select's disabled state.
 */
export function getModelsForBrand(brand: string | null): CarModelOption[] {
  const row = findBrand(brand)
  if (!row) return []
  return [...row.models]
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ name, brand: row.brand }))
}

/** True when `model` actually belongs to `brand` — used to clear a stale model on brand change. */
export function isModelOfBrand(brand: string | null, model: string | null): boolean {
  if (!model) return false
  const row = findBrand(brand)
  return row ? row.models.includes(model) : false
}

/** Selectable years, newest first. */
export function getYears(): number[] {
  const years: number[] = []
  for (let y = NEWEST_YEAR; y >= OLDEST_YEAR; y--) years.push(y)
  return years
}

/**
 * Price index for a brand, defaulting to 1.0 for unknown/absent — mirroring
 * `app/rag/brand_index.py`. Display only; the backend applies the real multiplier.
 */
export function getBrandIndex(brand: string | null): number {
  return findBrand(brand)?.index ?? 1.0
}
