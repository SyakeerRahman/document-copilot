import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { supabase } from '@/lib/supabase'

type Mode = 'sign-in' | 'sign-up'

export function LoginPage() {
  const { session, loading } = useAuth()
  const location = useLocation()
  const [mode, setMode] = useState<Mode>('sign-in')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (!loading && session) return <Navigate to={from} replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const credentials = { email: String(form.get('email')), password: String(form.get('password')) }

    setPending(true)
    setError(null)
    setNotice(null)
    const { data, error } =
      mode === 'sign-in'
        ? await supabase.auth.signInWithPassword(credentials)
        : await supabase.auth.signUp({ ...credentials, options: { emailRedirectTo: window.location.origin } })
    setPending(false)

    if (error) {
      setError(error.message)
      return
    }
    // With email confirmation on, sign-up returns no session until the link is clicked.
    if (mode === 'sign-up' && !data.session) setNotice('Check your email for a confirmation link, then sign in.')
  }

  const signingIn = mode === 'sign-in'

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{signingIn ? 'Sign in' : 'Create an account'}</CardTitle>
          <CardDescription>Document Copilot answers questions from SEC filings, with sources.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Work email</Label>
              <Input id="email" name="email" type="email" autoComplete="email" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={signingIn ? 'current-password' : 'new-password'}
                minLength={6}
                required
              />
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {notice && (
              <Alert>
                <AlertDescription>{notice}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? 'Please wait…' : signingIn ? 'Sign in' : 'Create account'}
            </Button>
            <Button
              type="button"
              variant="link"
              onClick={() => {
                setMode(signingIn ? 'sign-up' : 'sign-in')
                setError(null)
                setNotice(null)
              }}
            >
              {signingIn ? 'No account yet? Create one' : 'Already have an account? Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
