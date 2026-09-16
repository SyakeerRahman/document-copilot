import type { UIMessage } from 'ai'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { getMessages, getThread, type Thread } from '@/lib/api'
import { describeError } from '@/lib/http'

type Loaded = { thread: Thread; messages: UIMessage[] }

export function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!threadId) return
    let cancelled = false
    Promise.all([getThread(threadId), getMessages(threadId)]).then(
      ([thread, messages]) => !cancelled && setLoaded({ thread, messages }),
      (err: unknown) => !cancelled && setError(describeError(err)),
    )
    return () => {
      cancelled = true
    }
  }, [threadId])

  if (error) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4 sm:p-6">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Link to="/" className="text-sm underline">
          Back to your chats
        </Link>
      </div>
    )
  }

  if (!loaded) return <p className="p-6 text-sm text-muted-foreground">Loading chat…</p>

  // Keyed by thread so switching chats starts a fresh useChat instance with that thread's history.
  return <ChatPanel key={loaded.thread.id} threadId={loaded.thread.id} initialMessages={loaded.messages} />
}
