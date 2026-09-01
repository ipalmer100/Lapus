// The application shell: which view is showing, and the state shared between them.
//
// No router. This is a desktop-style internal app served from a single origin,
// and the navigation is four places -- a router would add a dependency and a
// build-time base-path concern for no gain. View state lives here.

import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import type { ChangeRequestSummary, ChangeTarget, Health } from './types'
import { SpecExplorer } from './features/spec-search/SpecExplorer'
import { SpecWorkspace } from './features/spec-workspace/SpecWorkspace'
import { ChangeRequestsPage } from './features/change-request/ChangeRequestsPage'
import { ProposeChangeDrawer } from './features/change-request/ProposeChangeDrawer'
import { ParserHealth } from './features/admin/ParserHealth'
import './App.css'

type View = 'explorer' | 'spec' | 'requests' | 'admin'

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [view, setView] = useState<View>('explorer')
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null)
  const [target, setTarget] = useState<ChangeTarget | null>(null)
  // Confirmation after a change is added. Shown in place rather than
  // navigating away: users routinely propose several changes across sections
  // of one spec before submitting, and jumping to the request each time would
  // make them walk back for every one.
  const [notice, setNotice] = useState<{ requestId: number; field: string } | null>(null)
  const [drafts, setDrafts] = useState<ChangeRequestSummary[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  // Bumped whenever a change is saved or decided, so open views refetch and an
  // approved change appears over the specification straight away.
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => { void api.health().then(setHealth).catch(() => setHealth(null)) }, [])

  const refreshRequests = useCallback(async () => {
    try {
      const [draftList, submitted] = await Promise.all([
        api.listRequests({ status: 'DRAFT', mine: true }),
        api.listRequests({ status: 'SUBMITTED' }),
      ])
      setDrafts(draftList)
      setPendingCount(submitted.length)
    } catch {
      // A failed count must not take the whole app down; the badge just stays put.
    }
  }, [])

  useEffect(() => { void refreshRequests() }, [refreshRequests, refreshToken])

  const openSpec = (id: number) => { setDocumentId(id); setView('spec') }
  const changed = () => setRefreshToken((n) => n + 1)

  if (health && health.status === 'unavailable') {
    return (
      <div className="startup-error">
        <h1>Lapus cannot open the specification database</h1>
        <p>{health.detail}</p>
        <p className="muted">
          Set <code>LAPUS_DATABASE_URL</code> to the <code>Spec_Stage.db</code> the parser
          produced, then restart Lapus.
        </p>
      </div>
    )
  }

  return (
    <div className="app">
      <nav className="app-nav">
        <span className="brand" onClick={() => setView('explorer')}>Lapus</span>
        <button type="button" className={view === 'explorer' || view === 'spec' ? 'active' : ''}
                onClick={() => setView('explorer')}>
          Specifications
        </button>
        <button type="button" className={view === 'requests' ? 'active' : ''}
                onClick={() => { setView('requests'); setSelectedRequestId(null) }}>
          Change requests
          {pendingCount > 0 && <span className="nav-badge" title="Awaiting review">{pendingCount}</span>}
        </button>
        {health?.user?.is_approver && (
          <button type="button" className={view === 'admin' ? 'active' : ''} onClick={() => setView('admin')}>
            Parser health
          </button>
        )}
        <span className="nav-spacer" />
        {health?.database && (
          <span className="nav-status" title={health.database.staging_source}>
            {health.database.document_count.toLocaleString()} specifications
            {health.database.staging_is_readonly && (
              <span className="chip chip-ok" title="Parser-owned data is opened read-only; Lapus cannot modify it">
                source protected
              </span>
            )}
          </span>
        )}
        {health?.user && <span className="nav-user">{health.user.email}</span>}
      </nav>

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
              setView('requests')
              setNotice(null)
            }}
          >
            Review and submit
          </button>
          <button type="button" className="notice-dismiss" aria-label="Dismiss" onClick={() => setNotice(null)}>
            &times;
          </button>
        </div>
      )}

      <main className="app-main">
        {view === 'explorer' && <SpecExplorer onOpenSpec={openSpec} />}
        {view === 'spec' && documentId !== null && (
          <SpecWorkspace
            documentId={documentId}
            canPropose
            refreshToken={refreshToken}
            onBack={() => setView('explorer')}
            onPropose={setTarget}
          />
        )}
        {view === 'requests' && (
          <ChangeRequestsPage
            onOpenSpec={openSpec}
            onChanged={changed}
            selectedRequestId={selectedRequestId}
            onSelectRequest={setSelectedRequestId}
          />
        )}
        {view === 'admin' && <ParserHealth onOpenSpec={openSpec} />}
      </main>

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
