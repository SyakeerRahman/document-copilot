import type { UIMessage } from 'ai'
import { cn } from '@/lib/utils'

export function MessageBubble({ message }: { message: UIMessage }) {
  const text = message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
  const fromUser = message.role === 'user'

  return (
    <div className={cn('flex', fromUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap',
          fromUser ? 'bg-primary text-primary-foreground' : 'bg-muted',
        )}
      >
        {text}
      </div>
    </div>
  )
}
