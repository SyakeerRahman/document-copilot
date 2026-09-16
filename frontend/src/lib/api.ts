import type { UIMessage } from 'ai'
import { request, type RequestOptions } from '@/lib/http'

type Options = Omit<RequestOptions, 'body'>

export const api = {
  get: <T>(path: string, options?: Options) => request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: Options) => request<T>('POST', path, { ...options, body }),
  put: <T>(path: string, body?: unknown, options?: Options) => request<T>('PUT', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: Options) => request<T>('PATCH', path, { ...options, body }),
  delete: <T>(path: string, options?: Options) => request<T>('DELETE', path, options),
}

// Must match MAX_USER_MESSAGE_CHARS in backend/app/chat/messages.py.
export const MAX_MESSAGE_CHARS = 4000

export type Thread = {
  id: string
  title: string | null
  createdAt: string
  updatedAt: string
}

export const listThreads = () => api.get<Thread[]>('/threads')
export const createThread = () => api.post<Thread>('/threads')
export const getThread = (threadId: string) => api.get<Thread>(`/threads/${threadId}`)
export const getMessages = (threadId: string) => api.get<UIMessage[]>(`/threads/${threadId}/messages`)

// Matches app/chat/messages.py:citation_data. Sent as the `data-citations` part of an assistant message.
export type Citation = {
  handle: string
  chunkId: string
  ticker: string
  companyName: string
  filingType: string
  fiscalYear: number
  filingDate: string
  pageNumber: number
  pageLabel: string | null
  section: string
  subsection: string | null
  sourceUrl: string
  excerpt: string
}
