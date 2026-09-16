// useChat reports three kinds of failure: fetch itself failing (API down, offline, CORS), an HTTP error
// before the stream starts (the Error message is the response body, usually FastAPI's {"detail": ...}),
// and an error part inside the stream (the Error message is the backend's own sentence).

const KNOWN_DETAILS: Record<string, string> = {
  'Missing or invalid access token': 'Your session has ended. Sign out, sign in again, and resend your question.',
  'Thread belongs to another user': 'You do not have access to this chat.',
  'Thread not found': 'This chat no longer exists.',
  'Authentication service unavailable': 'Sign-in is unavailable right now. Try again in a minute.',
}

export function describeChatError(error: Error): string {
  const message = error.message
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return 'Could not reach the Document Copilot service. Check your connection and try again.'
  }
  const detail = readDetail(message)
  if (detail === null) return message
  return KNOWN_DETAILS[detail] ?? detail
}

function readDetail(message: string): string | null {
  try {
    const body: unknown = JSON.parse(message)
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') return body.detail
  } catch {
    // Not JSON: the message is already a sentence.
  }
  return null
}
