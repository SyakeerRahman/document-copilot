import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Composer } from '@/components/chat/Composer'
import { EmptyChat } from '@/components/chat/EmptyChat'
import { MessageBubble } from '@/components/chat/MessageBubble'
import { SourcePanel } from '@/components/chat/SourcePanel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { Citation } from '@/lib/api'
import { describeChatError } from '@/lib/chatErrors'
import { apiUrl, authHeaders } from '@/lib/http'

type Props = {
  threadId: string
  initialMessages: UIMessage[]
}

export function ChatPanel({ threadId, initialMessages }: Props) {
  const [transport] = useState(
    () =>
      new DefaultChatTransport({
        api: apiUrl('/chat/stream'),
        // The API loads history from the database, so only the newest user message is sent. "Try again"
        // resends it, which is why this looks for the last user message rather than the last message.
        prepareSendMessagesRequest: async ({ messages }) => ({
          body: { threadId, message: messages.findLast((message) => message.role === 'user') },
          headers: await authHeaders(),
        }),
      }),
  )
  // The API sends no answer text until the answer passes its citation check. Until then it sends transient
  // status parts ("Searching AMZN fiscal 2025: AWS operating income"), which arrive here and are never saved.
  const [progress, setProgress] = useState<string | null>(null)
  const [openCitation, setOpenCitation] = useState<Citation | null>(null)
  const { messages, sendMessage, regenerate, status, error, stop, clearError } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    onData: (part) => {
      if (part.type === 'data-status') setProgress((part.data as { text: string }).text)
    },
  })
  const busy = status === 'submitted' || status === 'streaming'

  const ask = useCallback(
    (text: string) => {
      setProgress(null)
      clearError()
      void sendMessage({ text })
    },
    [sendMessage, clearError],
  )

  const retry = () => {
    setProgress(null)
    clearError()
    // A failed turn saves nothing on the server, so the same question is sent again.
    void regenerate()
  }

  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, busy, error])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 sm:p-6">
          {messages.length === 0 && <EmptyChat onAsk={ask} />}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} onOpenCitation={setOpenCitation} />
          ))}
          {busy && (
            <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
              {progress ?? 'Starting'}
            </p>
          )}
          {error && !busy && (
            <Alert variant="destructive">
              <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
                <span>{describeChatError(error)}</span>
                <Button size="sm" variant="outline" onClick={retry}>
                  Try again
                </Button>
              </AlertDescription>
            </Alert>
          )}
          <div ref={endRef} />
        </div>
      </div>
      <Composer busy={busy} onSend={ask} onStop={() => void stop()} />
      <SourcePanel citation={openCitation} onClose={() => setOpenCitation(null)} />
    </div>
  )
}
