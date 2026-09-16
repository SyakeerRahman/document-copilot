import type { Citation } from '@/lib/api'
import { shortSource } from '@/lib/citations'

type Props = {
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}

export function SourceList({ citations, onOpenCitation }: Props) {
  return (
    <div className="mt-3 border-t pt-2">
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">Sources</p>
      <ul className="flex flex-col gap-1">
        {citations.map((citation) => (
          <li key={citation.handle}>
            <button
              type="button"
              onClick={() => onOpenCitation(citation)}
              className="flex w-full items-baseline gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <span className="shrink-0 font-mono text-primary">{citation.handle}</span>
              <span className="min-w-0">
                <span className="font-medium">{shortSource(citation)}</span>
                <span className="block truncate text-muted-foreground">
                  {citation.section}
                  {citation.subsection ? ` > ${citation.subsection}` : ''}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
