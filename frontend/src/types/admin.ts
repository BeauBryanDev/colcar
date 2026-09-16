/**
 * Admin dashboard contract — mirrors app/schemas/auth.py and app/schemas/admin.py.
 *
 * Responses are camelCase (the backend's alias generator); requests are
 * snake_case, exactly as `ApiRequest` expects. That split is deliberate on the
 * backend — see CLAUDE.md, "Conventions" — so it is mirrored rather than
 * "fixed" here.
 *
 * The one exception: `InspectionDetail.pricing` / `.compliance` are bare dicts
 * on the backend, so the alias generator never touches them and everything
 * nested stays **snake_case** (`total_cop`, not `totalCop`). Same rule as the
 * customer-facing report.
 */

//  Auth   

/** Mirrors UserRole in app/models/user.py. Ranked: user < staff < admin. */
export type UserRole = 'user' | 'staff' | 'admin'

export interface AdminUser {
  username: string
  role: UserRole
  fullName: string | null
  email: string | null
  phoneNumber: string | null
  active: boolean
}

export interface LoginResponse {
  accessToken: string
  tokenType: string
  /** The exact `exp` that was signed — never recompute it from expiresIn. */
  expiresAt: string
  expiresIn: number
  user: AdminUser
}

/** Request bodies are snake_case (ApiRequest). */
export interface LoginRequest {
  username: string
  password: string
}

export interface UserCreateRequest {
  username: string
  password: string
  role?: UserRole
  full_name?: string | null
  email?: string | null
  phone_number?: string | null
  active?: boolean
}

/**
 * Partial update. A key that is **absent** leaves the field alone; an explicit
 * `null` clears it. The backend uses `exclude_unset`, so never send a key you
 * do not mean to change — sending `email: null` erases the email.
 */
export interface UserUpdateRequest {
  password?: string
  role?: UserRole
  full_name?: string | null
  email?: string | null
  phone_number?: string | null
  active?: boolean
}

export interface UserListResponse {
  users: AdminUser[]
  total: number
}

export interface DeletedResponse {
  username: string
  deleted: boolean
}

// Appointments  
/** Mirrors AppointmentStatus in app/models/appointment.py. */
export type AppointmentStatus =
  | 'programada'
  | 'confirmada'
  | 'cancelada'
  | 'atendida'

export interface AppointmentSummary {
  codigo: string
  appointmentId: string
  inspectionId: string
  status: AppointmentStatus
  customerName: string
  customerPhone: string
  customerEmail: string
  brand: string | null
  vehicleModel: string | null
  year: number | string | null
  licensePlate: string | null
  /** UTC, with a `Z` — the models re-attach the timezone pymongo drops. */
  scheduledFor: string
  /** The human string in workshop time; prefer this for display. */
  scheduledLocal: string
  timezone: string
  /** Already net of any discount — see `discountCode`. */
  estimatedRepairCostCop: number | null
  discountCode: string | null
  /** What the customer quotes at the counter, e.g. TKT-000042. */
  ticketNumber: string | null
  discountPercent: number | null
  originalCostCop: number | null
  notes: string | null
  createdAt: string
}

export interface AppointmentListResponse {
  appointments: AppointmentSummary[]
  total: number
}

/** The full booking, as returned by GET /admin/appointments/{codigo}. */
export interface AppointmentDetail extends AppointmentSummary {
  /** What the customer was quoted at the moment they booked. Bare dict → snake_case. */
  inspectionSnapshot?: Record<string, unknown> | null
  customer?: { name: string; phone: string; email: string }
  carInfo?: Record<string, unknown>
}

/**
 * Move a booking to another slot. Mirrors `AppointmentScheduleUpdate` in
 * app/schemas/admin.py — snake_case, like every request body.
 *
 * Two bare strings in **workshop-local** time, not an ISO instant: the backend
 * hands them to the same `parse_slot` the agent's `reschedule_appointment` tool
 * uses, so the workshop-hours, no-Sunday and future-date rules are identical
 * whether a booking moves from this calendar or from chat.
 */
export interface AppointmentScheduleRequest {
  /** AAAA-MM-DD */
  fecha: string
  /** HH:MM, 24h */
  hora: string
}

export interface AppointmentFilters {
  date_from?: string
  date_to?: string
  status?: AppointmentStatus
  codigo?: string
  limit?: number
}

//  Inspections 
export interface InspectionSummary {
  inspectionId: string
  status: string
  createdAt: string
  completedAt: string | null
  brand: string | null
  vehicleModel: string | null
  year: number | string | null
  defectCount: number
  totalCop: number | null
  rechazoRtmProbable: boolean | null
  imagesAnalyzed: number
}

export interface InspectionListResponse {
  inspections: InspectionSummary[]
  total: number
}

/** One defect row inside a stored inspection — snake_case, it is a bare dict. */
export interface StoredDefect {
  pieza: string
  tipo_defecto: string
  severidad: string
  confidence?: number | null
  severity_basis?: string | null
  matched_part_name?: string | null
  match_containment?: number | null
  precio_exacto?: boolean | null
  total_cost_cop?: number | null
  fallback_level?: string | null
  causal_rechazo?: boolean | null
  clase_rechazo?: string | null
}

export interface InspectionDetail {
  inspectionId: string
  status: string
  createdAt: string
  completedAt: string | null
  vehicleInfo: Record<string, unknown>
  defects: StoredDefect[]
  /** Bare dicts: everything nested stays snake_case (`total_cop`). */
  pricing: Record<string, unknown> | null
  compliance: Record<string, unknown> | null
  resumenAgente: string | null
  totalCop: number | null
  rechazoRtmProbable: boolean | null
  imagesAnalyzed: number
}

export interface InspectionFilters {
  date_from?: string
  date_to?: string
  brand?: string
  rechazo_rtm_probable?: boolean
  limit?: number
}
