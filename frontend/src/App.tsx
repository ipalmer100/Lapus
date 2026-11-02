// The application shell.
//
// Follows Cobalt: a persistent spec sidebar beside a main panel whose mode
// tabs switch what is shown, filling the viewport, with each pane scrolling
// on its own. No router -- navigation is four places and the state lives here.

import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import type { ChangeRequestSummary, ChangeTarget, Health, SectionMeta, SpecFilter } from './types'
import { SpecSidebar } from './components/SpecSidebar'
import { ThemeToggle } from './components/ThemeToggle'
import { SpecWorkspace } from './features/spec-workspace/SpecWorkspace'
import { ChangeRequestsPage } from './features/change-request/ChangeRequestsPage'
import { ProposeChangeDrawer } from './features/change-request/ProposeChangeDrawer'
import { ParserHealth } from './features/admin/ParserHealth'
import { MassEditGrid } from './features/mass-edit/MassEditGrid'
import './App.css'

type Mode = 'specification' | 'mass-edit' | 'requests' | 'admin'

const NO_FILTER: SpecFilter = { query: '', material: '', includeMissing: false }

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [mode, setMode] = useState<Mode>('specification')
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [filter, setFilter] = useState<SpecFilter>(NO_FILTER)
  const [sections, setSections] = useState<SectionMeta[]>([])
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null)
  const [target, setTarget] = useState<ChangeTarget | null>(null)
  const [drafts, setDrafts] = useState<ChangeRequestSummary[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [notice, setNotice] = useState<{ requestId: number; field: string } | null>(null)
  // Bumped whenever a change is saved or decided, so open panes refetch and an
  // approved change appears over the specification straight away.
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    void api.health().then(setHealth).catch(() => setHealth(null))
    // The section contract, so the grid's section list comes from the same
    // config file the backend validates against.
    void api.listSections().then(setSections).catch(() => setSections([]))
  }, [])

  const refreshRequests = useCallback(async () => {
    try {
      const [draftList, submitted] = await Promise.all([
        api.listRequests({ status: 'DRAFT', mine: true }),
        api.listRequests({ status: 'SUBMITTED' }),
      ])
      setDrafts(draftList)
      setPendingCount(submitted.length)
    } catch {
      // A failed count must not take the app down; the badge just stays put.
    }
  }, [])

  useEffect(() => {
    void refreshRequests()
  }, [refreshRequests, refreshToken])

  const changed = () => setRefreshToken((n) => n + 1)
  const openSpec = (id: number) => {
    setDocumentId(id)
    setMode('specification')
  }

  if (health && health.status === 'unavailable') {
    return (
      <div className="startup-error">
        <h1>Lapus cannot open the specification database</h1>
        <p>{health.detail}</p>
        <p className="muted">
          Set <code>LAPUS_DATABASE_URL</code> to the specification database the parser
          produced, then restart Lapus.
        </p>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <SpecSidebar
        selectedId={documentId}
        onSelect={openSpec}
        documentCount={health?.database?.document_count ?? null}
        refreshToken={refreshToken}
        filter={filter}
        onFilterChange={setFilter}
      />

      <div className="main-panel">
        <div className="mode-tabs">
          <button
            type="button"
            className={mode === 'specification' ? 'active' : ''}
            onClick={() => setMode('specification')}
          >
            Specification
          </button>
          <button
            type="button"
            className={mode === 'mass-edit' ? 'active' : ''}
            onClick={() => setMode('mass-edit')}
            title="One section across every specification in scope"
          >
            Mass Edit
          </button>
          <button
            type="button"
            className={mode === 'requests' ? 'active' : ''}
            onClick={() => setMode('requests')}
          >
            Change requests
            {pendingCount > 0 && <span className="tab-badge">{pendingCount}</span>}
          </button>
          {health?.user?.is_approver && (
            <button
              type="button"
              className={mode === 'admin' ? 'active' : ''}
              onClick={() => setMode('admin')}
              title="How the parser got on with the source documents"
            >
              Parser health
            </button>
          )}

          <span className="tab-spacer" />
          <ThemeToggle />
          {health?.database?.staging_is_readonly && (
            <span
              className="chip chip-ok"
              title="Parser-owned specification data is opened read-only; Lapus cannot modify it"
            >
              source protected
            </span>
          )}
          <input
            className="who-input"
            value={health?.user?.email ?? ''}
            readOnly
            title="The identity recorded against change requests you raise"
          />
        </div>

        {notice && (
          <div className="notice-bar" role="status">
            <span>
              <strong>{notice.field}</strong> added to change request #{notice.requestId}.
            </span>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSelectedRequestId(notice.requestId)
                setMode('requests')
                setNotice(null)
              }}
            >
              Review and submit
            </button>
            <button
              type="button"
              className="notice-dismiss"
              aria-label="Dismiss"
              onClick={() => setNotice(null)}
            >
              &times;
            </button>
          </div>
        )}

        {mode === 'specification' &&
          (documentId !== null ? (
            <SpecWorkspace
              documentId={documentId}
              canPropose
              refreshToken={refreshToken}
              onPropose={setTarget}
            />
          ) : (
            <div className="empty-state">Select a specification from the list.</div>
          ))}

        {mode === 'mass-edit' && (
          <MassEditGrid
            filter={filter}
            sections={sections}
            openDrafts={drafts}
            onStaged={(requestId) => {
              setSelectedRequestId(requestId)
              setMode('requests')
              changed()
            }}
          />
        )}

        {mode === 'requests' && (
          <ChangeRequestsPage
            onOpenSpec={openSpec}
            onChanged={changed}
            selectedRequestId={selectedRequestId}
            onSelectRequest={setSelectedRequestId}
          />
        )}

        {mode === 'admin' && <ParserHealth onOpenSpec={openSpec} />}
      </div>

      {target && (
        <ProposeChangeDrawer
          target={target}
          openDrafts={drafts}
          onClose={() => setTarget(null)}
          onSaved={(requestId) => {
            setNotice({ requestId, field: target.fieldLabel })
            setTarget(null)
            changed()
          }}
        />
      )}
    </div>
  )
}
