/**
 * Every admin endpoint, in one place.
 *
 * Filters are passed as `params` rather than hand-built query strings so axios
 * drops `undefined` keys for us — sending `?status=` would filter for the empty
 * status and return nothing.
 *
 * **Dates go to the backend as bare `YYYY-MM-DD`.** It reads a naive date as
 * *workshop-local* (America/Bogota) and widens `date_to` to the end of that
 * day. Sending an ISO instant with a `Z` instead would filter by UTC days and
 * put five hours of every evening on the wrong date.
 */

import { apiClient } from '@/services/api'
import type {
  AdminUser,
  AppointmentDetail,
  AppointmentFilters,
  AppointmentListResponse,
  AppointmentScheduleRequest,
  AppointmentStatus,
  AppointmentSummary,
  DeletedResponse,
  InspectionDetail,
  InspectionFilters,
  InspectionListResponse,
  UserCreateRequest,
  UserListResponse,
  UserUpdateRequest,
} from '@/types/admin'

/** Strip empty values so an untouched filter field never narrows the query. */
function clean<T extends object>(filters: T): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(
      ([, v]) => v !== undefined && v !== null && v !== '',
    ),
  )
}

export const adminService = {
  // ─── Appointments ────────────────────────────────────────────────────────

  async listAppointments(
    filters: AppointmentFilters = {},
  ): Promise<AppointmentListResponse> {
    const { data } = await apiClient.get<AppointmentListResponse>(
      '/admin/appointments',
      { params: clean(filters) },
    )
    return data
  },

  async getAppointment(codigo: string): Promise<AppointmentDetail> {
    const { data } = await apiClient.get<AppointmentDetail>(
      `/admin/appointments/${encodeURIComponent(codigo)}`,
    )
    return data
  },

  /**
   * Move a booking through its lifecycle. The backend enforces the transition
   * table (`atendida` and `cancelada` are terminal) and answers 409 with code
   * `transicion_invalida` — the UI hides illegal moves, but the backend is what
   * actually decides.
   */
  async updateAppointmentStatus(
    codigo: string,
    status: AppointmentStatus,
    notes?: string,
  ): Promise<AppointmentSummary> {
    const { data } = await apiClient.patch<AppointmentSummary>(
      `/admin/appointments/${encodeURIComponent(codigo)}`,
      clean({ status, notes }),
    )
    return data
  },

  /**
   * Drag a booking to another slot.
   *
   * `fecha`/`hora` are workshop-local strings, never an ISO instant — the
   * backend reads them with the agent tool's own `parse_slot`. Two rejections
   * are expected and distinct: **400 `horario_invalido`** (past, Sunday, or
   * outside 08–18) and **409 `horario_ocupado`** (another active booking holds
   * that hour — `uniq_active_slot`, the real double-booking guard). A terminal
   * booking answers 409 `transicion_invalida`.
   */
  async rescheduleAppointment(
    codigo: string,
    payload: AppointmentScheduleRequest,
  ): Promise<AppointmentSummary> {
    const { data } = await apiClient.patch<AppointmentSummary>(
      `/admin/appointments/${encodeURIComponent(codigo)}/schedule`,
      payload,
    )
    return data
  },

  // ─── Inspections ─────────────────────────────────────────────────────────

  async listInspections(
    filters: InspectionFilters = {},
  ): Promise<InspectionListResponse> {
    const { data } = await apiClient.get<InspectionListResponse>(
      '/admin/inspections',
      { params: clean(filters) },
    )
    return data
  },

  async getInspection(inspectionId: string): Promise<InspectionDetail> {
    const { data } = await apiClient.get<InspectionDetail>(
      `/admin/inspections/${encodeURIComponent(inspectionId)}`,
    )
    return data
  },

  // ─── Users (admin only — a staff token gets 403) ──────────────────────────

  async listUsers(filters: {
    role?: string
    active?: boolean
    limit?: number
  } = {}): Promise<UserListResponse> {
    const { data } = await apiClient.get<UserListResponse>('/admin/users', {
      params: clean(filters),
    })
    return data
  },

  async getUser(username: string): Promise<AdminUser> {
    const { data } = await apiClient.get<AdminUser>(
      `/admin/users/${encodeURIComponent(username)}`,
    )
    return data
  },

  async createUser(payload: UserCreateRequest): Promise<AdminUser> {
    const { data } = await apiClient.post<AdminUser>('/admin/users', payload)
    return data
  },

  /**
   * Partial update. Only send keys you mean to change — the backend uses
   * `exclude_unset`, so an omitted field is left alone while an explicit
   * `null` clears it.
   */
  async updateUser(
    username: string,
    payload: UserUpdateRequest,
  ): Promise<AdminUser> {
    const { data } = await apiClient.patch<AdminUser>(
      `/admin/users/${encodeURIComponent(username)}`,
      payload,
    )
    return data
  },

  async deleteUser(username: string): Promise<DeletedResponse> {
    const { data } = await apiClient.delete<DeletedResponse>(
      `/admin/users/${encodeURIComponent(username)}`,
    )
    return data
  },
}

export default adminService
