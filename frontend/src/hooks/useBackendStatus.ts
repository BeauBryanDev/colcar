import { useEffect, useState } from 'react'
import axios from 'axios'
import { BASE_URL } from '@/services/api'

export type BackendStatus = 'checking' | 'online' | 'offline'

// /health is mounted at the backend root, not under /api, so it is derived
// from the API base rather than requested through apiClient.
const HEALTH_URL = `${BASE_URL.replace(/\/api\/?$/, '')}/health`
const POLL_MS = 30_000
const TIMEOUT_MS = 5_000

export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const { data } = await axios.get(HEALTH_URL, { timeout: TIMEOUT_MS })
        // A 200 alone is not proof: a static host answers unknown paths with
        // index.html. Only the backend's own body counts as online.
        if (!cancelled) setStatus(data?.status === 'ok' ? 'online' : 'offline')
      } catch {
        if (!cancelled) setStatus('offline')
      }
    }

    check()
    const id = window.setInterval(check, POLL_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      cancelled = true
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return status
}




