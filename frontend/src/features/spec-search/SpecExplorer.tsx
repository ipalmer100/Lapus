// Finding a specification.
//
// Every filter is sent to the server; nothing is filtered in the browser. With
// ~14,000 specifications and their material rows behind them, loading a corpus
// to filter it client-side is not an option (CODEX_START_PROMPT.md).

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type SearchParams } from '../../api/client'
import type { SpecSummary } from '../../types'

const PAGE_SIZE = 25

interface Props {
  onOpenSpec: (documentId: number) => void
}

export function SpecExplorer({ onOpenSpec }: Props) {
  const [text, setText] = useState('')
  const [filters, setFilters] = useState({
    customer: '', spec_number: '', item: '', filename: '', structure: '', raw_material: '',
  })
  const [showFilters, setShowFilters] = useState(false)
  const [includeMissing, setIncludeMissing] = useState(false)
  const [results, setResults] = useState<SpecSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Guards against an earlier, slower search overwriting a later one's results
  // when the user keeps typing.
  const requestSeq = useRef(0)

  const runSearch = useCallback(async (nextOffset: number) => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    const params: SearchParams = {
      q: text || undefined,
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '')),
      include_missing: includeMissing,
      limit: PAGE_SIZE,
      offset: nextOffset,
    }
    try {
      const response = await api.searchSpecs(params)
      if (seq !== requestSeq.current) return
      setResults(response.results)
      setTotal(response.total)
      setOffset(response.offset)
    } catch (err) {
      if (seq !== requestSeq.current) return
      setError(err instanceof ApiError ? err.message : 'Search failed.')
      setResults([])
      setTotal(0)
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [text, filters, includeMissing])

  // Debounced so typing a spec number does not fire a query per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => { void runSearch(0) }, 250)
    return () => clearTimeout(timer)
  }, [runSearch])

  const activeFilterCount = Object.values(filters).filter((v) => v !== '').length

  return (
    <div className="explorer">
      <div className="explorer-search">
        <input
          type="search"
          className="search-input"
          placeholder="Search by customer, spec number, item, structure, raw material or file name"
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <button
          type="button"
          className={showFilters ? 'filter-toggle active' : 'filter-toggle'}
          onClick={() => setShowFilters((open) => !open)}
        >
          Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
        </button>
      </div>

      {showFilters && (
        <div className="filter-panel">
          {([
            ['customer', 'Customer'],
            ['spec_number', 'Specification number'],
            ['item', 'Item / finished good'],
            ['structure', 'Structure'],
            ['raw_material', 'Raw material, supplier or item code'],
            ['filename', 'Source file name'],
          ] as const).map(([key, label]) => (
            <label key={key} className="filter-field">
              <span>{label}</span>
              <input
                type="text"
                value={filters[key]}
                onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}
              />
            </label>
          ))}
          <label className="filter-check">
            <input
              type="checkbox"
              checked={includeMissing}
              onChange={(e) => setIncludeMissing(e.target.checked)}
            />
            <span>Include specifications whose source file is missing</span>
          </label>
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setFilters({ customer: '', spec_number: '', item: '', filename: '', structure: '', raw_material: '' })
              setIncludeMissing(false)
            }}
          >
            Clear filters
          </button>
        </div>
      )}

      <div className="explorer-status">
        {loading ? 'Searching…' : `${total.toLocaleString()} specification${total === 1 ? '' : 's'}`}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!loading && !error && results.length === 0 && (
        <div className="empty-state">
          <p>No specifications match that search.</p>
          <p className="empty-hint">
            Try part of a spec number or customer name, or search for a raw material
            to find every specification that uses it.
          </p>
        </div>
      )}

      {results.length > 0 && (
        <table className="results-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Specification</th>
              <th>Item</th>
              <th>Structure</th>
              <th>Rev</th>
              <th>Issued</th>
            </tr>
          </thead>
          <tbody>
            {results.map((spec) => (
              <tr
                key={spec.document_id}
                onClick={() => onOpenSpec(spec.document_id)}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => { if (e.key === 'Enter') onOpenSpec(spec.document_id) }}
              >
                <td>{spec.customer ?? <span className="muted">Not stated</span>}</td>
                <td>
                  <span className="spec-number">{spec.spec_number ?? spec.filename}</span>
                  {spec.is_present === 0 && (
                    <span className="chip chip-warn" title="The source Word document was not found on the last parser run">
                      source missing
                    </span>
                  )}
                </td>
                <td>{spec.item ?? <span className="muted">—</span>}</td>
                <td className="structure-cell">{spec.structure_description ?? <span className="muted">—</span>}</td>
                <td>{spec.revision_number ?? '—'}</td>
                <td>{spec.date_of_issue ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {total > PAGE_SIZE && (
        <div className="pager">
          <button type="button" disabled={offset === 0 || loading}
                  onClick={() => void runSearch(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}
          </span>
          <button type="button" disabled={offset + PAGE_SIZE >= total || loading}
                  onClick={() => void runSearch(offset + PAGE_SIZE)}>
            Next
          </button>
        </div>
      )}
    </div>
  )
}
