import apiClient from './api'
import type { InspectionReport, VisionResult, InspectionStatus } from '@/types'

/**
 * Mirrors `InspectionResultResponse` in app/schemas/inspection.py.
 *
 * There is no `/reports/*` router on the backend — the report and the vision
 * payload both come from `GET /api/inspections/{id}/results`, and `report` is
 * null until the agent loop has finished.
 */
export interface InspectionResults {
  sessionId: string
  status: InspectionStatus
  vision: VisionResult | null
  report: InspectionReport | null
  completedAt: string | null
}

export const reportService = {
  /** Full results for a session: vision payload + agent report. */
  async getResults(sessionId: string): Promise<InspectionResults> {
    const res = await apiClient.get<InspectionResults>(`/inspections/${sessionId}/results`)
    return res.data
  },

  /** Just the agent report, or null if the agent has not produced one. */
  async getReport(sessionId: string): Promise<InspectionReport | null> {
    const { report } = await reportService.getResults(sessionId)
    return report
  },

  /** Client-side JSON download of an already-fetched report. */
  triggerJSONDownload(report: InspectionReport, filename = 'car-inspector-report.json'): void {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
