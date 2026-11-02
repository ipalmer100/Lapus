// Reading one specification.
//
// All eleven sections on one continuous scroll, as Cobalt's spec detail does
// it -- the point being that nobody should have to click through eleven tabs
// to find the Bill of Materials. The left rail jumps to a section rather than
// swapping which one is mounted, and highlights whichever is currently in
// view.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ChangeTarget, Section, SpecChangeHistory, SpecDetail } from '../../types'
import { blank } from '../../display'
import { SectionView } from './SectionView'
import { SpecChangeHistoryView } from './SpecChangeHistoryView'

interface Props {
  documentId: number
  canPropose: boolean
  onPropose: (target: ChangeTarget) => void
  refreshToken: number
}

export function SpecWorkspace({ documentId, canPropose, onPropose, refreshToken }: Props) {
  const [detail, setDetail] = useState<SpecDetail | null>(null)
  const [sections, setSections] = useState<Section[] | null>(null)
  const [history, setHistory] = useState<SpecChangeHistory | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [current, setCurrent] = useState(1)
  const [error, setError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const sectionRefs = useRef(new Map<number, HTMLElement>())

  const load = useCallback(async () => {
    setError(null)
    try {
      // Both at once: the header alone is not worth a round trip when the
      // sections are what the page is for.
      const [spec, all] = await Promise.all([
        api.getSpec(documentId),
        api.getAllSections(documentId),
      ])
      setDetail(spec)
      setSections(all)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not open this specification.')
    }
  }, [documentId])

  useEffect(() => {
    setDetail(null)
    setSections(null)
    setShowHistory(false)
    setCurrent(1)
    void load()
  }, [load, refreshToken])

  useEffect(() => {
    if (!showHistory) return
    void api.getSpecHistory(documentId).then(setHistory).catch(() => setHistory(null))
  }, [documentId, showHistory, refreshToken])

  // Highlight whichever section is nearest the top of the scrolling pane.
  useEffect(() => {
    const pane = scrollRef.current
    if (!pane || !sections) return
    const onScroll = () => {
      let nearest = 1
      let best = Infinity
      for (const [number, element] of sectionRefs.current) {
        const offset = Math.abs(element.getBoundingClientRect().top - pane.getBoundingClientRect().top)
        if (offset < best) {
          best = offset
          nearest = number
        }
      }
      setCurrent(nearest)
    }
    pane.addEventListener('scroll', onScroll, { passive: true })
    return () => pane.removeEventListener('scroll', onScroll)
  }, [sections])

  const jumpTo = (number: number) => {
    sectionRefs.current.get(number)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const availability = useMemo(() => {
    const map = new Map<number, { empty: boolean; overrides: number }>()
    for (const section of sections ?? []) {
      map.set(section.number, { empty: section.is_empty, overrides: section.override_count })
    }
    return map
  }, [sections])

  if (error) return <div className="error-banner">{error}</div>
  if (!detail || !sections) return <div className="loading">Opening specification…</div>

  const h = detail.header
  const status = detail.staging_status

  return (
    <div className="workspace">
      <header className="spec-header">
        <h1>{blank(h.spec_number) ?? blank(h.filename) ?? `Document ${h.document_id}`}</h1>
        <p className="spec-subtitle">
          {blank(h.customer) ?? 'Customer not stated'}
          {blank(h.item) && <> &middot; Item {blank(h.item)}</>}
          {blank(h.revision_number) && <> &middot; Revision {blank(h.revision_number)}</>}
        </p>
        {blank(h.structure_description) && (
          <p className="spec-structure">{blank(h.structure_description)}</p>
        )}
        <div className="spec-badges">
          {h.is_present === 0 && (
            <span className="chip chip-warn" title="The source document was not found on the last parser run">
              Source file missing
            </span>
          )}
          {detail.approved_override_count > 0 && (
            <span className="chip chip-change">
              {detail.approved_override_count} approved change
              {detail.approved_override_count === 1 ? '' : 's'}
            </span>
          )}
          <button type="button" className="link-button" onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? 'Hide change history' : 'Change history'}
          </button>
        </div>
        <details className="source-provenance">
          <summary>Source document</summary>
          <dl>
            <div><dt>File</dt><dd>{h.filename}</dd></div>
            <div><dt>Path</dt><dd>{h.relative_path}</dd></div>
            <div><dt>Staged</dt><dd>{h.imported_at}</dd></div>
            <div><dt>Parser</dt><dd>{h.parser_version}</dd></div>
            <div><dt>Document id</dt><dd>{h.document_id}</dd></div>
            {status && (
              <div>
                <dt>Mapping</dt>
                <dd>
                  {status.mapped_source_tables} table
                  {status.mapped_source_tables === 1 ? '' : 's'} mapped
                  {status.supplemental_source_tables > 0 && `, ${status.supplemental_source_tables} supplemental`}
                  {status.unmapped_source_tables > 0 && `, ${status.unmapped_source_tables} unmapped`}
                </dd>
              </div>
            )}
          </dl>
        </details>
      </header>

      {showHistory && <SpecChangeHistoryView history={history} />}

      <div className="workspace-body">
        <nav className="section-rail" aria-label="Sections">
          <ol>
            {sections.map((section) => {
              const meta = availability.get(section.number)
              return (
                <li key={section.number}>
                  <button
                    type="button"
                    className={[
                      section.number === current ? 'current' : '',
                      meta?.empty ? 'empty' : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => jumpTo(section.number)}
                  >
                    <span className="section-number">{String(section.number).padStart(2, '0')}</span>
                    <span className="section-label">{section.label}</span>
                    {(meta?.overrides ?? 0) > 0 && (
                      <span className="section-dot" title="Contains approved changes" />
                    )}
                  </button>
                </li>
              )
            })}
          </ol>
        </nav>

        <div className="sections-scroll" ref={scrollRef}>
          {sections.map((section) => (
            <section
              key={section.number}
              className="detail-section"
              ref={(element) => {
                if (element) sectionRefs.current.set(section.number, element)
                else sectionRefs.current.delete(section.number)
              }}
            >
              <h2>
                {String(section.number).padStart(2, '0')} &nbsp;{section.label}
                {!section.is_empty && section.is_repeating && (
                  <span className="section-count"> &nbsp;· {section.rows.length} rows</span>
                )}
              </h2>
              <SectionView
                section={section}
                documentId={documentId}
                canPropose={canPropose}
                onPropose={onPropose}
              />
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
