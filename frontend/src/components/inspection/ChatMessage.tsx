import React from 'react'
import Markdown from 'react-markdown'
// GFM: tables, strikethrough, task lists, autolinks. Without this plugin
// react-markdown renders a table as literal |---|---| pipes.
import remarkGfm from 'remark-gfm'
import { FiUser } from 'react-icons/fi'
import type { ChatMessage as ChatMessageType } from '@/types'
import chatIconUrl from '@/assets/chat_icon.svg'

interface ChatMessageProps {
  message: ChatMessageType
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isAgent = message.role === 'agent'

  if (isAgent) {
    return (
      <div className="flex items-start gap-3 max-w-[90%]">
        {/* Avatar */}
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-brand-navy border-2 border-brand-yellow overflow-hidden">
          <img src={chatIconUrl} alt="Car-Lens" className="w-full h-full object-cover" />
        </div>

        {/* Bubble */}
        <div className="flex flex-col gap-1">
          <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
            {/* The agent replies in Spanish markdown: headings, bullet lists and
                bolded COP figures. Rendered as text it shows raw ** and -. */}
            <div
              className={[
                'text-brand-navy text-base leading-relaxed font-medium',
                '[&_p]:mb-2 [&_p:last-child]:mb-0',
                '[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-1',
                '[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-2 [&_ol]:flex [&_ol]:flex-col [&_ol]:gap-1',
                '[&_strong]:font-extrabold [&_strong]:text-brand-blue',
                '[&_h1]:font-extrabold [&_h1]:text-lg [&_h1]:mb-1',
                '[&_h2]:font-extrabold [&_h2]:text-base [&_h2]:mb-1 [&_h2]:uppercase',
                '[&_h3]:font-extrabold [&_h3]:text-base [&_h3]:mb-1',
                '[&_code]:bg-brand-navy/10 [&_code]:rounded [&_code]:px-1 [&_code]:text-sm',
                '[&_a]:text-brand-blue [&_a]:underline',
                // Tables scroll inside the bubble instead of widening it.
                '[&_.md-table-wrap]:overflow-x-auto [&_.md-table-wrap]:my-2',
                '[&_table]:w-full [&_table]:text-sm [&_table]:border-collapse',
                '[&_thead]:bg-brand-navy/5',
                '[&_th]:text-left [&_th]:font-extrabold [&_th]:px-2 [&_th]:py-1.5',
                '[&_th]:border [&_th]:border-brand-navy/20 [&_th]:whitespace-nowrap',
                '[&_td]:border [&_td]:border-brand-navy/15 [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top',
                '[&_tbody_tr:nth-child(even)]:bg-brand-navy/[0.03]',
                '[&_blockquote]:border-l-4 [&_blockquote]:border-brand-yellow [&_blockquote]:pl-3 [&_blockquote]:italic',
              ].join(' ')}
            >
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // A COP quote table is wide; let it scroll rather than blow
                  // out the chat column.
                  table: ({ children }) => (
                    <div className="md-table-wrap">
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {message.content}
              </Markdown>
            </div>
          </div>
          <span className="text-white/50 text-xs pl-1">{message.timestamp}</span>
        </div>
      </div>
    )
  }

  // User bubble — right-aligned
  return (
    <div className="flex items-end gap-3 max-w-[82%] self-end ml-auto">
      <div className="flex flex-col items-end gap-1">
        <div className="bg-brand-blue rounded-2xl rounded-br-sm px-4 py-3 shadow-sm">
          <p className="text-white text-base leading-relaxed whitespace-pre-wrap font-medium">
            {message.content}
          </p>
        </div>
        <span className="text-white/50 text-xs pr-1">{message.timestamp}</span>
      </div>
      {/* User avatar */}
      <div className="flex-shrink-0 w-10 h-10 rounded-full bg-brand-blue/60 border-2 border-brand-blue flex items-center justify-center">
        <FiUser className="w-5 h-5 text-white" />
      </div>
    </div>
  )
}

export default ChatMessage
