import { useEffect, useState } from 'react'
import { getCorpus, type CorpusCompany } from '@/lib/api'

// Examples from the client brief, each naming a company and a fiscal year: search filters on both, and a
// question without a year often retrieves the wrong year.
const EXAMPLES = [
  { ticker: 'AMZN', text: 'How did AWS operating income compare with North America and International in fiscal 2025?' },
  { ticker: 'AAPL', text: "How did Apple's net sales by product category change in fiscal 2025?" },
  { ticker: 'NVDA', text: 'What did NVIDIA say about customer concentration in fiscal 2025?' },
  { ticker: 'MSFT', text: 'What risks does Microsoft describe from developing and using AI in fiscal 2025?' },
]

function yearsText(years: number[]): string {
  const sorted = [...years].sort((a, b) => a - b)
  const consecutive = sorted.every((year, i) => i === 0 || year === sorted[i - 1] + 1)
  return consecutive && sorted.length > 1 ? `fiscal ${sorted[0]} to ${sorted.at(-1)}` : `fiscal ${sorted.join(', ')}`
}

export function EmptyChat({ onAsk }: { onAsk: (question: string) => void }) {
  const [corpus, setCorpus] = useState<CorpusCompany[] | null>(null)

  useEffect(() => {
    let cancelled = false
    // The coverage list helps but is not required: if it fails to load, the examples still work.
    getCorpus().then(
      (result) => !cancelled && setCorpus(result),
      () => !cancelled && setCorpus([]),
    )
    return () => {
      cancelled = true
    }
  }, [])

  const tickers = new Set(corpus?.map((company) => company.ticker))
  const examples = corpus && corpus.length > 0 ? EXAMPLES.filter((example) => tickers.has(example.ticker)) : EXAMPLES

  return (
    <div className="flex flex-col gap-4 py-6">
      <div>
        <h2 className="text-lg font-semibold">Ask about the filings</h2>
        <p className="text-sm text-muted-foreground">
          Every answer cites the filing, page, and passage it comes from. Name the company and the fiscal year for the
          best results.
        </p>
      </div>

      {corpus && corpus.length > 0 && (
        <div className="rounded-lg border p-3 text-sm">
          <p className="mb-1 font-medium">What the corpus covers</p>
          <ul className="text-muted-foreground">
            {corpus.map((company) => (
              <li key={company.ticker}>
                {company.companyName} ({company.ticker}): Form 10-K, {yearsText(company.fiscalYears)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">Try a question</p>
        {examples.map((example) => (
          <button
            key={example.text}
            type="button"
            onClick={() => onAsk(example.text)}
            className="rounded-lg border px-3 py-2 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {example.text}
          </button>
        ))}
      </div>
    </div>
  )
}
