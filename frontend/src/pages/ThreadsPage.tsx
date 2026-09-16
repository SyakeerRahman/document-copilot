import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { createThread, listThreads, type Thread } from '@/lib/api'
import { describeError } from '@/lib/http'

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function ThreadsPage() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    listThreads().then(
      (result) => !cancelled && setThreads(result),
      (err: unknown) => !cancelled && setError(describeError(err)),
    )
    return () => {
      cancelled = true
    }
  }, [])

  async function startChat() {
    setCreating(true)
    setError(null)
    try {
      const thread = await createThread()
      navigate(`/chat/${thread.id}`)
    } catch (err) {
      setError(describeError(err))
      setCreating(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 overflow-y-auto p-4 sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Your chats</h1>
        <Button onClick={() => void startChat()} disabled={creating}>
          {creating ? 'Starting…' : 'Start a chat'}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {threads === null && !error && <p className="text-sm text-muted-foreground">Loading chats…</p>}

      {threads?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No chats yet. Start one and ask a question about a filing, for example how Apple&apos;s revenue mix
          changed between 2021 and 2025.
        </p>
      )}

      {threads && threads.length > 0 && (
        <ul className="flex flex-col divide-y rounded-lg border">
          {threads.map((thread) => (
            <li key={thread.id}>
              <Link to={`/chat/${thread.id}`} className="flex flex-col gap-1 px-4 py-3 hover:bg-muted">
                <span className="truncate font-medium">{thread.title ?? 'Untitled chat'}</span>
                <span className="text-xs text-muted-foreground">{dateFormat.format(new Date(thread.updatedAt))}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
