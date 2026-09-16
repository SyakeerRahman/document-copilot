import type { Citation } from '@/lib/api'

// Minimal source list so answers can be checked now. Architecture step 13 replaces it with the full citation UI.
export function SourceList({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-3 border-t pt-2">
      <p className="mb-1 text-xs font-medium text-muted-foreground">Sources</p>
      <ol className="flex flex-col gap-1">
        {citations.map((citation) => (
          <li key={citation.handle} className="text-xs">
            <details>
              <summary className="cursor-pointer">
                <span className="font-mono">[{citation.handle}]</span> {citation.companyName} {citation.filingType},
                fiscal {citation.fiscalYear}, page {citation.pageLabel ?? citation.pageNumber}, {citation.section}
                {citation.subsection ? ` > ${citation.subsection}` : ''}
              </summary>
              <div className="mt-1 rounded border bg-background p-2">
                <p className="max-h-48 overflow-y-auto whitespace-pre-wrap">{citation.excerpt}</p>
                <a className="mt-1 inline-block underline" href={citation.sourceUrl} target="_blank" rel="noreferrer">
                  Open filing on SEC.gov
                </a>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </div>
  )
}
