// Parser health. Admin-only, and deliberately the only place mapping
// confidence, unmapped tables and table names are shown at all: a
// manufacturing user reading a specification should never meet them
// (AGENTS.md, UX rules).

import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { AdminExceptions, AdminStagingStatus } from '../../types'

interface Props {
  onOpenSpec: (documentId: number) => void
}

export function ParserHealth({ onOpenSpec }: Props) {
  const [status, setStatus] = useState<AdminStagingStatus | null>(null)
  const [exceptions, setExceptions] = useState<AdminExceptions | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.adminStagingStatus(), api.adminExceptions()])
      .then(([s, e]) => { setStatus(s); setExceptions(e) })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load parser health.'))
  }, [])

  if (error) return <div className="error-banner">{error}</div>
  if (!status || !exceptions) return <div className="loading">Loading parser health…</div>

  const s = status.summary
  const stats: { label: string; value: string | number; tone?: string }[] = [
    { label: 'Specifications staged', value: s.total_documents },
    { label: 'Source file present', value: s.present_documents },
    { label: 'Source file missing', value: s.missing_documents, tone: s.missing_documents ? 'warn' : undefined },
    { label: 'Tables mapped', value: s.mapped_tables },
    { label: 'Supplemental tables', value: s.supplemental_tables },
    { label: 'Unmapped tables', value: s.unmapped_tables, tone: s.unmapped_tables ? 'warn' : undefined },
    { label: 'Documents that failed', value: s.ingestion_errors, tone: s.ingestion_errors ? 'bad' : undefined },
  ]

  return (
    <div className="admin-page">
      <header className="admin-head">
        <h1>Parser health</h1>
        <p className="muted">
          Last staged {s.last_import ?? 'unknown'} &middot;{' '}
          {s.parser_version_breakdown.map((v) => `${v.parser_version} (${v.document_count})`).join(', ')}
        </p>
      </header>

      <div className="stat-grid">
        {stats.map((stat) => (
          <div key={stat.label} className={`stat-card${stat.tone ? ` stat-${stat.tone}` : ''}`}>
            <span className="stat-value">{stat.value.toLocaleString?.() ?? stat.value}</span>
            <span className="stat-label">{stat.label}</span>
          </div>
        ))}
      </div>

      <section>
        <h2>Change requests</h2>
        <div className="stat-grid">
          {['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED'].map((key) => (
            <div key={key} className="stat-card">
              <span className="stat-value">{status.change_request_counts[key] ?? 0}</span>
              <span className="stat-label">{key.charAt(0) + key.slice(1).toLowerCase()}</span>
            </div>
          ))}
        </div>
      </section>

      {exceptions.ingestion_errors.length > 0 && (
        <section>
          <h2>Documents that could not be staged</h2>
          <p className="panel-note">
            These files produced no specification record at all and need attention before the next parser run.
          </p>
          <table className="admin-table">
            <thead><tr><th>File</th><th>Error</th><th>Detail</th><th>When</th></tr></thead>
            <tbody>
              {exceptions.ingestion_errors.map((e) => (
                <tr key={e.id}>
                  <td>{e.relative_path ?? e.filename}</td>
                  <td>{e.error_type ?? '—'}</td>
                  <td className="muted">{e.error_message ?? '—'}</td>
                  <td>{e.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h2>Specifications needing attention</h2>
        {status.needs_attention.length === 0 ? (
          <p className="section-empty">Every staged specification mapped cleanly.</p>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Specification</th><th>Mapped</th><th>Supplemental</th>
                <th>Unmapped</th><th>Errors</th><th>Lowest confidence</th><th>Present</th>
              </tr>
            </thead>
            <tbody>
              {status.needs_attention.map((doc) => (
                <tr key={doc.document_id}>
                  <td>
                    <button type="button" className="link-button" onClick={() => onOpenSpec(doc.document_id)}>
                      {doc.relative_path}
                    </button>
                  </td>
                  <td>{doc.mapped_source_tables}</td>
                  <td>{doc.supplemental_source_tables}</td>
                  <td className={doc.unmapped_source_tables ? 'cell-warn' : undefined}>{doc.unmapped_source_tables}</td>
                  <td className={doc.table_errors ? 'cell-bad' : undefined}>{doc.table_errors}</td>
                  <td>{doc.minimum_mapping_confidence?.toFixed(2) ?? '—'}</td>
                  <td>{doc.is_present ? 'Yes' : <span className="cell-warn">No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>Supplemental and unmapped source tables</h2>
        <p className="panel-note">
          Content the parser kept rather than forced into a numbered section. Supplemental tables
          are real manufacturing content that belongs to no section; unmapped tables matched nothing at all.
        </p>
        {exceptions.unmapped_tables.length === 0 ? (
          <p className="section-empty">Nothing outstanding.</p>
        ) : (
          <table className="admin-table">
            <thead>
              <tr><th>Specification</th><th>Heading in the document</th><th>Classification</th><th>Suggested section</th><th>How it was matched</th></tr>
            </thead>
            <tbody>
              {exceptions.unmapped_tables.map((t) => (
                <tr key={t.id}>
                  <td>
                    <button type="button" className="link-button" onClick={() => onOpenSpec(t.document_id)}>
                      {t.relative_path}
                    </button>
                  </td>
                  <td>{t.preceding_heading ?? <span className="muted">No heading</span>}</td>
                  <td>
                    <span className={t.classification === 'unmapped' ? 'chip chip-warn' : 'chip'}>
                      {t.classification ?? 'unknown'}
                    </span>
                  </td>
                  <td>{t.suggested_section ?? <span className="muted">—</span>}</td>
                  <td className="muted">{t.mapping_method ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
