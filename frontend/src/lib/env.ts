// The only module allowed to read import.meta.env. Fails at boot so a missing
// variable surfaces as one clear error instead of a broken request later.
function required(name: string): string {
  const value: unknown = import.meta.env[name]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Missing required env var ${name}. Copy frontend/.env.example to frontend/.env and fill it in.`)
  }
  return value
}

export const env = {
  apiBaseUrl: required('VITE_API_BASE_URL').replace(/\/+$/, ''),
  supabaseUrl: required('VITE_SUPABASE_URL'),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY'),
} as const
