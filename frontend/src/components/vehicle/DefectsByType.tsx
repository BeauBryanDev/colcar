import React from 'react'
import type { DefectSummary } from '@/types'

interface DefectsByTypeProps {
  data: DefectSummary[]
}

export const DefectsByType: React.FC<DefectsByTypeProps> = ({ data }) => (
  <ul className="flex flex-col gap-2" aria-label="Defectos por tipo">
    {data.map((item) => (
      <li key={item.category} className="flex items-center gap-2 text-base">
        <span
          className="w-3.5 h-3.5 rounded-sm flex-shrink-0"
          style={{ backgroundColor: item.color }}
          aria-hidden="true"
        />
        <span className="font-semibold text-brand-navy flex-1">{item.category}</span>
        <span className="text-brand-navy tabular-nums font-medium">
          {item.count} ({item.percentage}%)
        </span>
      </li>
    ))}
  </ul>
)

export default DefectsByType
