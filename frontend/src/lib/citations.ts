import type { UIMessage } from 'ai'
import type { Citation } from '@/lib/api'

// Answers cite passages as [P3]. Turning each marker into a Markdown link lets the renderer draw it as a
// button. The fragment never navigates: CitationChip intercepts it.
export const CITATION_HREF_PREFIX = '#cite-'
const CITATION_MARKER = /\[(P\d+)\](?!\()/g

export function linkCitations(text: string): string {
  return text.replace(CITATION_MARKER, (_, handle: string) => `[${handle}](${CITATION_HREF_PREFIX}${handle})`)
}

export function citationsOf(message: UIMessage): Citation[] {
  const part = message.parts.find((p) => p.type === 'data-citations')
  return part && 'data' in part ? (part.data as Citation[]) : []
}

export function isUnverified(message: UIMessage): boolean {
  return message.parts.some((part) => part.type === 'data-unverified')
}

export function pageText(citation: Citation): string {
  return citation.pageLabel ? `page ${citation.pageLabel}` : `document page ${citation.pageNumber}`
}

export function shortSource(citation: Citation): string {
  return `${citation.ticker} ${citation.filingType}, FY${citation.fiscalYear}, ${pageText(citation)}`
}

const filingDateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' })

export function formatFilingDate(isoDate: string): string {
  return filingDateFormat.format(new Date(`${isoDate}T00:00:00Z`))
}
