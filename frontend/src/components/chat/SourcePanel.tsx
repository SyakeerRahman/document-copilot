import { Badge } from '@/components/ui/badge'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { Citation } from '@/lib/api'
import { formatFilingDate, pageText } from '@/lib/citations'

type Props = {
  citation: Citation | null
  onClose: () => void
}

export function SourcePanel({ citation, onClose }: Props) {
  return (
    <Sheet open={citation !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-xl">
        {citation && (
          <>
            <SheetHeader className="border-b">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {citation.handle}
                </Badge>
                <SheetTitle className="text-base">
                  {citation.companyName} ({citation.ticker})
                </SheetTitle>
              </div>
              <SheetDescription>
                Form {citation.filingType}, fiscal year {citation.fiscalYear}, filed{' '}
                {formatFilingDate(citation.filingDate)}
              </SheetDescription>
            </SheetHeader>

            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Page</dt>
                <dd>{pageText(citation)}</dd>
                <dt className="text-muted-foreground">Section</dt>
                <dd>{citation.section}</dd>
                {citation.subsection && (
                  <>
                    <dt className="text-muted-foreground">Subsection</dt>
                    <dd>{citation.subsection}</dd>
                  </>
                )}
              </dl>

              <figure className="flex flex-col gap-2">
                <figcaption className="text-xs font-medium text-muted-foreground">
                  Passage text, exactly as stored from the filing
                </figcaption>
                <blockquote className="rounded border bg-muted/40 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                  {citation.excerpt}
                </blockquote>
              </figure>

              <a
                href={citation.sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-primary underline underline-offset-4"
              >
                Open the full filing on SEC.gov
              </a>
              <p className="text-xs text-muted-foreground">
                The filing on SEC.gov has no page links. Search it for the section name or a phrase from the passage.
              </p>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
