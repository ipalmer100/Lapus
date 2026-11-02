// The persistent specification list.
//
// Shaped after Cobalt's sidebar -- search, filters that each say how many
// specs they hold, three-line rows, and a virtualized list -- with one
// necessary difference. Cobalt loads its whole vault into the browser and
// filters there; Lapus must not. The corpus is 5,179 specifications over
// ~47,000 material rows, and shipping that to a browser to filter is exactly
// what AGENTS.md forbids. So the search box drives a server query, and the
// list grows as it is scrolled rather than arriving whole.
//
// Virtualization still earns its place: a page of several hundred rows
// mounted as real DOM nodes is what made Cobalt's sidebar slow before it was
// virtualized, and the counts shown here come from the server's total, so the
// filter stays as trustworthy as Cobalt's ("nothing has gone missing, it has
// just moved").

import { useCallback, useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { api, ApiError, type SearchParams } from '../api/client'
import type { SpecSummary } from '../types'
import { blank } from '../display'

const PAGE = 100
const ROW_HEIGHT = 54

interface Props {
  selectedId: number | null
  onSelect: (documentId: number) => void
  documentCount: number | null
  refreshToken: number
}

export function SpecSidebar({ selectedId, onSelect, documentCount, refreshToken }: Props) {
  const [query, setQuery] = useState('')
  const [material, setMaterial] = useState('')
  const [includeMissing, setIncludeMissing] = useState(false)
  const [rows, setRows] = useState<SpecSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Guards against a slower earlier search overwriting a later one's results
  // while someone is still typing.
  const seq = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  const params = useCallback(
    (offset: number): SearchParams => ({
      q: query || undefined,
      raw_material: material || undefined,
      include_missing: includeMissing,
      limit: PAGE,
      offset,
    }),
    [query, material, includeMissing],
  )

  useEffect(() => {
    const id = ++seq.current
    setLoading(true)
    setError(null)
    const timer = setTimeout(() => {
      api
        .searchSpecs(params(0))
        .then((res) => {
          if (id !== seq.current) return
          setRows(res.results)
          setTotal(res.total)
          scrollRef.current?.scrollTo({ top: 0 })
        })
        .catch((err) => {
          if (id !== seq.current) return
          setError(err instanceof ApiError ? err.message : 'Search failed.')
          setRows([])
          setTotal(0)
        })
        .finally(() => {
          if (id === seq.current) setLoading(false)
        })
    }, 250)
    return () => clearTimeout(timer)
  }, [params, refreshToken])

  const loadMore = useCallback(() => {
    if (loadingMore || rows.length >= total) return
    const id = seq.current
    setLoadingMore(true)
    api
      .searchSpecs(params(rows.length))
      .then((res) => {
        if (id !== seq.current) return
        setRows((prev) => [...prev, ...res.results])
      })
      .catch(() => undefined)
      .finally(() => setLoadingMore(false))
  }, [loadingMore, rows.length, total, params])

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  // Fetch the next page once the last rendered row comes into view.
  const items = virtualizer.getVirtualItems()
  useEffect(() => {
    const last = items[items.length - 1]
    if (last && last.index >= rows.length - 5) loadMore()
  }, [items, rows.length, loadMore])

  const filtered = query.trim() !== '' || material.trim() !== '' || includeMissing

  return (
    <div className="sidebar">
      <div className="sidebar-root">
        <span className="sidebar-brand">Lapus</span>
        <span>{documentCount !== null && `${documentCount.toLocaleString()} staged`}</span>
      </div>

      <input
        className="sidebar-search"
        placeholder="Search spec, customer, item…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      <input
        className="sidebar-search"
        placeholder="Raw material, supplier or code…"
        value={material}
        onChange={(e) => setMaterial(e.target.value)}
        title="Find every specification that uses a material"
      />

      <div className="sidebar-status-filter">
        <button
          type="button"
          className={`status-toggle ${!includeMissing ? 'on' : ''}`}
          onClick={() => setIncludeMissing(false)}
          title="Only specifications whose source document was found on the last parser run"
        >
          Present
        </button>
        <button
          type="button"
          className={`status-toggle ${includeMissing ? 'on' : ''}`}
          onClick={() => setIncludeMissing(true)}
          title="Also show specifications whose source document has gone missing"
        >
          Include missing
        </button>
      </div>

      <div className="sidebar-search-count">
        {loading
          ? 'Searching…'
          : filtered && documentCount !== null
            ? `${total.toLocaleString()} of ${documentCount.toLocaleString()}`
            : `${total.toLocaleString()} specification${total === 1 ? '' : 's'}`}
      </div>

      {error && <div className="sidebar-empty">{error}</div>}

      <div className="sidebar-list" ref={scrollRef}>
        <div style={{ position: 'relative', height: virtualizer.getTotalSize(), width: '100%' }}>
          {items.map((vi) => {
            const spec = rows[vi.index]
            if (!spec) return null
            const name = blank(spec.spec_number) ?? blank(spec.filename) ?? `Document ${spec.document_id}`
            const item = blank(spec.item)
            const revision = blank(spec.revision_number)
            return (
              <button
                key={spec.document_id}
                ref={virtualizer.measureElement}
                data-index={vi.index}
                type="button"
                className={`sidebar-item ${spec.document_id === selectedId ? 'selected' : ''}`}
                style={{ transform: `translateY(${vi.start}px)` }}
                onClick={() => onSelect(spec.document_id)}
                title={spec.relative_path}
              >
                <span className="sidebar-item-name">
                  {name}
                  {spec.is_present === 0 && <span className="sidebar-flag">missing</span>}
                </span>
                <span className="sidebar-item-folder">
                  {blank(spec.customer) ?? 'Customer not stated'}
                </span>
                <span className="sidebar-item-meta">
                  {item ? `Item ${item}` : 'No item'}
                  {revision && ` · Rev ${revision}`}
                </span>
              </button>
            )
          })}
        </div>
        {!loading && rows.length === 0 && !error && (
          <div className="sidebar-empty">
            No specifications match. Try part of a spec number, a customer, or a raw material.
          </div>
        )}
        {loadingMore && <div className="sidebar-loading">Loading more…</div>}
      </div>
    </div>
  )
}
