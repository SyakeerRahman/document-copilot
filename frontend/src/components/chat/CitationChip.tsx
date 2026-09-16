import type { Citation } from '@/lib/api'
import { shortSource } from '@/lib/citations'

type Props = {
  handle: string
  citation: Citation | undefined
  onOpen: (citation: Citation) => void
}

export function CitationChip({ handle, citation, onOpen }: Props) {
  // Grounding rejects answers with unknown handles, so this only happens for malformed stored data.
  if (!citation) return <span className="font-mono text-xs text-muted-foreground">[{handle}]</span>

  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      title={`${citation.companyName}: ${shortSource(citation)}`}
      aria-label={`Source ${handle}: ${shortSource(citation)}`}
      className="mx-0.5 inline-flex items-center rounded border border-primary/30 bg-background px-1 align-baseline font-mono text-[0.7rem] leading-4 text-primary hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {handle}
    </button>
  )
}
