import React from 'react'
import chatIconUrl from '@/assets/chat_icon.svg'
import { Loading } from '@/components/common/Loading'

/** Animated "Car-Lens is typing…" bubble */
export const BubbleChat: React.FC = () => (
  <div className="flex items-start gap-2 max-w-[88%]">
    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-brand-navy border-2 border-brand-yellow overflow-hidden">
      <img src={chatIconUrl} alt="Car-Lens" className="w-full h-full object-cover" />
    </div>
    <div className="bg-white/95 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm flex items-center">
      <Loading variant="dots" size="sm" color="navy" />
    </div>
  </div>
)

export default BubbleChat
