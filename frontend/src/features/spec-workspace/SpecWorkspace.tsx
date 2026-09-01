// Reading one specification.
//
// The persistent header carries identity and provenance; the left rail walks
// the eleven sections in source-document order. Sections are fetched when
// opened rather than all at once -- eleven queries per spec across a corpus
// this size is worth avoiding, and it keeps the first paint fast.

import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ChangeTarget, Section, SpecChangeHistory, SpecDetail } from '../../types'
import { SectionView } from './SectionView'
import { SpecChangeHistoryView } from './SpecChangeHistoryView'

interface Props {
  documentId: number
  canPropose: boolean
  onBack: () => void
  onPropose: (target: ChangeTarget) => void
  refreshToken: number
}

export function SpecWorkspace({ documentId, canPropose, onBack, onPropose, refreshToken }: Props) {
  const [detail, setDetail] = useState<SpecDetail | null>(null)
  const [activeSection, setActiveSection] = useState(1)
  const [section, setSection] = useState<Section | null>(null)
  const [history, setHistory] = useState<SpecChangeHistory | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadingSection, setLoadingSection] = useState(false)

  const loadDetail = useCallback(async () => {
    try {
      setDetail(await api.getSpec(documentId))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not open this specification.')
    }
  }, [documentId])

  useEffect(() => { void loadDetail() }, [loadDetail, refreshToken])

  useEffect(() => {
    let cancelled = false
    setLoadingSection(true)
    api.getSection(documentId, activeSection)
      .then((s) => { if (!cancelled) setSection(s) })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load section.') })
      .finally(() => { if (!cancelled) setLoadingSection(false) })
    return () => { cancelled = true }
  }, [documentId, activeSection, refreshToken])

  useEffect(() => {
    if (!showHistory) return
    void api.getSpecHistory(documentId).then(setHistory).catch(() => setHistory(null))
  }, [documentId, showHistory, refreshToken])

  if (error) return <div className="error-banner">{error}</div>
  if (!detail) return <div className="loading">Opening specification…</div>

  const h = detail.header
  const status = detail.staging_status

  return (
    <div className="workspace">
      <header className="spec-header">
        <button type="button" className="link-button back" onClick={onBack}>&larr; All specifications</button>
        <div className="spec-identity">
          <h1>{h.spec_number ?? h.filename}</h1>
          <p className="spec-subtitle">
            {h.customer ?? 'Customer not stated'}
            {h.item && <> &middot; Item {h.item}</>}
            {h.revision_number && <> &middot; Revision {h.revision_number}</>}
          </p>
          {h.structure_description && <p className="spec-structure">{h.structure_description}</p>}
        </div>
        <div className="spec-badges">
          {h.is_present === 0 && (
            <span className="chip chip-warn" title="The source Word document was not found on the last parser run">
              Source file missing
            </span>
          )}
          {detail.approved_override_count > 0 && (
            <span className="chip chip-change">
              {detail.approved_override_count} approved change{detail.approved_override_count === 1 ? '' : 's'}
            </span>
          )}
          <button type="button" className="link-button" onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? 'Hide change history' : 'Change history'}
          </button>
        </div>
        {/* Source traceability, kept quiet: useful for support, not something a
            manufacturing user needs to read every time. */}
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
                  {status.mapped_source_tables} table{status.mapped_source_tables === 1 ? '' : 's'} mapped
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
        <nav className="section-nav" aria-label="Specification sections">
          <ol>
            {detail.sections.map((s) => (
              <li key={s.number}>
                <button
                  type="button"
                  className={[
                    s.number === activeSection ? 'active' : '',
                    s.is_empty ? 'empty' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={() => setActiveSection(s.number)}
                >
                  <span className="section-number">{String(s.number).padStart(2, '0')}</span>
                  <span className="section-label">{s.label}</span>
                  {s.override_count > 0 && <span className="section-dot" title="Contains approved changes" />}
                  {s.is_empty && <span className="section-none">none</span>}
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <section className="section-content" aria-live="polite">
          {loadingSection && !section ? (
            <div className="loading">Loading…</div>
          ) : section ? (
            <>
              <h2 className="section-heading">
                {String(section.number).padStart(2, '0')} &nbsp;{section.label}
              </h2>
              <SectionView
                section={section}
                documentId={documentId}
                canPropose={canPropose}
                onPropose={onPropose}
              />
            </>
          ) : null}
        </section>
      </div>
    </div>
  )
}
