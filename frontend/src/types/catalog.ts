/**
 * Vehicle catalog types — the shape of `src/data/carModels.json`, which is a
 * copy of `app/rag/car_models.json` on the backend.
 *
 * The brand is what selects the price index server-side (`app/rag/brand_index.py`),
 * so `CarBrand.brand` strings must match the backend's spelling exactly. `index`
 * is carried for display/transparency only — all pricing arithmetic happens in
 * Python, never here.
 */

/** One row of carModels.json. */
export interface CarBrand {
  brand: string
  index: number
  models: string[]
}

/** A model flattened together with the brand that owns it. */
export interface CarModelOption {
  /** Model name, e.g. "Logan". */
  name: string
  /** Owning brand, e.g. "Dacia" — models are not unique across brands. */
  brand: string
}

/**
 * What the three selects produce. Sent with the first upload as the
 * `brand` / `vehicle_model` / `year` form fields — note `vehicleModel`,
 * because `model` already names the detection panel.
 */
export interface VehicleSelection {
  brand: string | null
  vehicleModel: string | null
  year: number | null
}
