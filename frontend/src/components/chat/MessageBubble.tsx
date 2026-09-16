import type { UIMessage } from 'ai'
import { SourceList } from '@/components/chat/SourceList'
import type { Citation } from '@/lib/api'
import { cn } from '@/lib/utils'

function citationsOf(message: UIMessage): Citation[] {
  const part = message.parts.find((p) => p.type === 'data-citations')
  return part && 'data' in part ? (part.data as Citation[]) : []
}

export function MessageBubble({ message }: { message: UIMessage }) {
  const text = message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
  const fromUser = message.role === 'user'
  // Set when the draft answer failed the citation check; the text is then a notice, not an answer.
  const unverified = message.parts.some((part) => part.type === 'data-unverified')
  const citations = fromUser ? [] : citationsOf(message)

  // An assistant message exists as soon as the stream starts, but its text arrives only once verified.
  if (!fromUser && !text) return null

  return (
    <div className={cn('flex', fromUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-4 py-2 text-sm',
          fromUser && 'bg-primary text-primary-foreground',
          !fromUser && !unverified && 'bg-muted',
          unverified && 'border border-amber-500/60 bg-amber-50 text-amber-950 dark:bg-amber-950/40 dark:text-amber-100',
        )}
      >
        {unverified && <p className="mb-1 text-xs font-semibold">Not verified</p>}
        <div className="whitespace-pre-wrap">{text}</div>
        {citations.length > 0 && <SourceList citations={citations} />}
      </div>
    </div>
  )
}
