/**
 * Login, token storage, and the session the dashboard renders from.
 *
 * The token lives in `localStorage` under the key `apiClient`'s request
 * interceptor already reads (`car_inspector_token`), so simply storing it is
 * enough to authenticate every later call — there is no second place to wire.
 *
 * **The stored token is never trusted on its own.** It is a signed blob the
 * browser cannot verify; `AuthProvider` calls `GET /auth/me` on load and lets
 * the backend decide. What is cached alongside it is only a hint used to paint
 * the shell before that round trip returns.
 */

import { apiClient } from '@/services/api'
import type {
  AdminUser,
  LoginRequest,
  LoginResponse,
} from '@/types/admin'

const TOKEN_KEY = 'car_inspector_token'
const USER_KEY = 'car_inspector_user'
const EXPIRES_KEY = 'car_inspector_token_expires'

export const authService = {
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const { data } = await apiClient.post<LoginResponse>(
      '/auth/login',
      credentials,
    )
    authService.storeSession(data)
    return data
  },

  /** Ask the backend who this token belongs to. The only real check. */
  async me(): Promise<AdminUser> {
    const { data } = await apiClient.get<AdminUser>('/auth/me')
    return data
  },

  storeSession(data: LoginResponse): void {
    localStorage.setItem(TOKEN_KEY, data.accessToken)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    localStorage.setItem(EXPIRES_KEY, data.expiresAt)
  },

  clearSession(): void {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(EXPIRES_KEY)
  },

  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY)
  },

  /** The cached account — a painting hint, not proof of anything. */
  getCachedUser(): AdminUser | null {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as AdminUser
    } catch {
      return null
    }
  },

  /**
   * True when the stored `exp` has already passed.
   *
   * Only ever used to skip a doomed `/auth/me` round trip — an unexpired token
   * still proves nothing, since the account may have been disabled since it was
   * issued (the backend re-reads `active` on every request).
   */
  isExpired(): boolean {
    const expiresAt = localStorage.getItem(EXPIRES_KEY)
    if (!expiresAt) return false
    return new Date(expiresAt).getTime() <= Date.now()
  },
}

export default authService
