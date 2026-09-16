import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

const DEFAULT_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  readonly status: number | null
  // True when no HTTP response arrived at all: API down, offline, CORS, or timeout.
  readonly isNetworkError: boolean

  constructor(message: string, status: number | null, isNetworkError = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.isNetworkError = isNetworkError
  }
}

export type RequestOptions = {
  body?: unknown
  timeoutMs?: number
  signal?: AbortSignal
}

export function apiUrl(path: string): string {
  return `${env.apiBaseUrl}${path}`
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  const headers: Record<string, string> = { Accept: 'application/json', ...(await authHeaders()) }

  let body: string | undefined
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(apiUrl(path), { method, headers, body, signal })
  } catch (error) {
    if (options.signal?.aborted) throw error
    if (timeout.aborted) throw new ApiError('The server took too long to respond.', null, true)
    // fetch rejects only when there is no response: API not running, offline, or blocked by CORS.
    throw new ApiError(`Could not reach the API at ${env.apiBaseUrl}.`, null, true)
  }

  if (!response.ok) throw new ApiError(await readErrorMessage(response), response.status)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json()
    if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
      return data.detail
    }
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`
}

export function describeError(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}
