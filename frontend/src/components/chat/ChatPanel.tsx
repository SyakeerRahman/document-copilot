import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'
import { useEffect, useRef, useState } from 'react'
import { Composer } from '@/components/chat/Composer'
import { MessageBubble } from '@/components/chat/MessageBubble'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
        // The API loads history from the database, so only the new message is sent.
        prepareSendMessagesRequest: async ({ messages }) => ({
          body: { threadId, message: messages.at(-1) },
          headers: await authHeaders(),
        }),
      }),
  )
  const { messages, sendMessage, status, error, stop } = useChat({ id: threadId, messages: initialMessages, transport })
  const busy = status === 'submitted' || status === 'streaming'

  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 sm:p-6">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Ask a question about the filings. Answers will cite the filing and page they came from.
            </p>
          )}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {status === 'submitted' && <p className="text-sm text-muted-foreground">Thinking…</p>}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          )}
          <div ref={endRef} />
        </div>
      </div>
      <Composer busy={busy} onSend={(text) => void sendMessage({ text })} onStop={() => void stop()} />
    </div>
  )
}
