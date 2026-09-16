import { Link, Outlet } from 'react-router'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { supabase } from '@/lib/supabase'

export function AppShell() {
  const { session } = useAuth()

  return (
    <div className="flex h-svh flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <Link to="/" className="font-semibold">
          Document Copilot
        </Link>
        <div className="flex min-w-0 items-center gap-3 text-sm">
          <span className="hidden truncate text-muted-foreground sm:inline">{session?.user.email}</span>
          <Button variant="outline" size="sm" onClick={() => void supabase.auth.signOut()}>
            Sign out
          </Button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
