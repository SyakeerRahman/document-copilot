import { useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CitationChip } from '@/components/chat/CitationChip'
import type { Citation } from '@/lib/api'
import { CITATION_HREF_PREFIX, linkCitations } from '@/lib/citations'

type Props = {
  text: string
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}

// react-markdown renders no raw HTML by default, so model output cannot inject markup.
export function AnswerMarkdown({ text, citations, onOpenCitation }: Props) {
  const byHandle = useMemo(() => new Map(citations.map((c) => [c.handle, c])), [citations])

  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        if (href?.startsWith(CITATION_HREF_PREFIX)) {
          const handle = href.slice(CITATION_HREF_PREFIX.length)
          return <CitationChip handle={handle} citation={byHandle.get(handle)} onOpen={onOpenCitation} />
        }
        return (
          <a href={href} target="_blank" rel="noreferrer" className="underline">
            {children}
          </a>
        )
      },
      p: ({ children }) => <p className="leading-relaxed [&:not(:first-child)]:mt-3">{children}</p>,
      ul: ({ children }) => <ul className="mt-2 list-disc space-y-1 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="mt-2 list-decimal space-y-1 pl-5">{children}</ol>,
      strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
      h1: ({ children }) => <p className="mt-3 font-semibold">{children}</p>,
      h2: ({ children }) => <p className="mt-3 font-semibold">{children}</p>,
      h3: ({ children }) => <p className="mt-3 font-semibold">{children}</p>,
      table: ({ children }) => (
        <div className="mt-3 overflow-x-auto rounded border bg-background">
          <table className="w-full border-collapse text-left text-xs">{children}</table>
        </div>
      ),
      th: ({ children }) => <th className="border-b bg-muted/60 px-2 py-1.5 font-semibold">{children}</th>,
      td: ({ children }) => <td className="border-b px-2 py-1.5 align-top tabular-nums">{children}</td>,
      code: ({ children }) => <code className="rounded bg-background px-1 font-mono text-xs">{children}</code>,
    }),
    [byHandle, onOpenCitation],
  )

  return (
    <div className="text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  )
}
