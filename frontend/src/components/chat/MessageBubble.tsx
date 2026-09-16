import type { UIMessage } from 'ai'
import { AnswerMarkdown } from '@/components/chat/AnswerMarkdown'
import { SourceList } from '@/components/chat/SourceList'
import type { Citation } from '@/lib/api'
import { citationsOf, isUnverified } from '@/lib/citations'
import { cn } from '@/lib/utils'

type Props = {
  message: UIMessage
  onOpenCitation: (citation: Citation) => void
}

export function MessageBubble({ message, onOpenCitation }: Props) {
  const text = message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
  const fromUser = message.role === 'user'

  // An assistant message exists as soon as the stream starts, but its text arrives only once verified.
  if (!fromUser && !text) return null

  if (fromUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
          {text}
        </div>
      </div>
    )
  }

  // Set when the draft answer failed the citation check; the text is then a notice, not an answer.
  const unverified = isUnverified(message)
  const citations = citationsOf(message)

  return (
    <div className="flex justify-start">
      <div
        className={cn(
          'max-w-[92%] rounded-lg px-4 py-3',
          unverified
            ? 'border border-amber-500/60 bg-amber-50 text-amber-950 dark:bg-amber-950/40 dark:text-amber-100'
            : 'bg-muted',
        )}
      >
        {unverified ? (
          <>
            <p className="mb-1 text-xs font-semibold">Not verified</p>
            <p className="text-sm">{text}</p>
          </>
        ) : (
          <AnswerMarkdown text={text} citations={citations} onOpenCitation={onOpenCitation} />
        )}
        {citations.length > 0 && <SourceList citations={citations} onOpenCitation={onOpenCitation} />}
      </div>
    </div>
  )
}
