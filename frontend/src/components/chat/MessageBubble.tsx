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
  const citations = fromUser ? [] : citationsOf(message)

  return (
    <div className={cn('flex', fromUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-4 py-2 text-sm',
          fromUser ? 'bg-primary text-primary-foreground' : 'bg-muted',
        )}
      >
        <div className="whitespace-pre-wrap">{text}</div>
        {citations.length > 0 && <SourceList citations={citations} />}
      </div>
    </div>
  )
}
