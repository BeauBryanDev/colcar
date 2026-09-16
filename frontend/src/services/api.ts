import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000, // 2 min for YOLO inference
  headers: {
    'Content-Type': 'application/json',
  },
})

// ─── Request interceptor ────────────────────────────────────────────────────
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('car_inspector_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ─── Response interceptor ───────────────────────────────────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const message =
        (error.response?.data as { detail?: string })?.detail ??
        error.message ??
        'Error desconocido'
      return Promise.reject(new Error(message))
    }
    return Promise.reject(error)
  },
)

export default apiClient
