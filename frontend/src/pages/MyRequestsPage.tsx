import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMyRequests, deleteRequest } from '../api/requests'
import RequestBadge from '../components/RequestBadge'
import RequestComments from '../components/RequestComments'
import RequestTimeline from '../components/RequestTimeline'

function WatchNowButton({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white text-xs font-semibold rounded-full transition-colors"
    >
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
      </svg>
      Watch Now
    </a>
  )
}

function NextStepHint({ req }: { req: any }) {
  if (!req.next_step_label) return null
  return (
    <p className="text-xs text-cyan-300">
      Next: {req.next_step_label}
      {req.next_step_by ? ` (by ${new Date(req.next_step_by).toLocaleDateString()})` : ''}
    </p>
  )
}

function EtaHint({ req }: { req: any }) {
  if (!req.eta_label) return null

  const etaConfidence: 'low' | 'medium' | 'high' =
    req.eta_confidence === 'high' || req.eta_confidence === 'medium' ? req.eta_confidence : 'low'
  const confidenceStyle = {
    high: 'text-emerald-300',
    medium: 'text-amber-300',
    low: 'text-slate-300',
  }[etaConfidence]

  return (
    <p className={`text-xs ${confidenceStyle}`}>
      ETA: {req.eta_label}
      {req.eta_start && req.eta_end
        ? ` (${new Date(req.eta_start).toLocaleDateString()} - ${new Date(req.eta_end).toLocaleDateString()})`
        : ''}
      {req.eta_confidence ? `, ${req.eta_confidence} confidence` : ''}
    </p>
  )
}

function PromiseSnapshot({ req }: { req: any }) {
  if (!req.promise_summary && !req.benchmark_label && !req.follow_up_label) return null

  const status: 'ahead' | 'on_track' | 'at_risk' | 'breached' | 'done' =
    req.promise_status === 'ahead' ||
    req.promise_status === 'on_track' ||
    req.promise_status === 'at_risk' ||
    req.promise_status === 'breached' ||
    req.promise_status === 'done'
      ? req.promise_status
      : 'on_track'

  const toneMap = {
    ahead: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    on_track: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200',
    at_risk: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    breached: 'border-red-500/30 bg-red-500/10 text-red-200',
    done: 'border-slate-600 bg-slate-800/80 text-slate-300',
  } as const
  const tone = toneMap[status]

  const labelMap = {
    ahead: 'Ahead of normal',
    on_track: 'On track',
    at_risk: 'Watch this one',
    breached: 'Past promise',
    done: 'Closed',
  } as const
  const label = labelMap[status]

  return (
    <div className={`rounded-lg border px-3 py-2 space-y-1 ${tone}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide">{label}</span>
        {req.benchmark_source && (
          <span className="text-[11px] opacity-75">
            {req.benchmark_source === 'media_type' ? 'Based on this media type' : 'Based on household history'}
          </span>
        )}
      </div>
      {req.promise_summary && <p className="text-xs">{req.promise_summary}</p>}
      {req.benchmark_label && <p className="text-xs opacity-90">Normal: {req.benchmark_label}</p>}
      {req.follow_up_label && (
        <p className="text-xs opacity-90">
          {req.follow_up_label}
          {req.follow_up_by ? ` (${new Date(req.follow_up_by).toLocaleDateString()})` : ''}
        </p>
      )}
    </div>
  )
}

function BlockerSnapshot({ req }: { req: any }) {
  if (!req.blocker_reason) return null

  return (
    <div className={`rounded-lg border px-3 py-2 space-y-1 ${req.blocker_is_overdue ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide">
          {req.blocker_is_overdue ? 'Review overdue' : 'Blocked, with next review set'}
        </span>
      </div>
      <p className="text-xs">{req.blocker_reason}</p>
      {req.blocker_note && <p className="text-xs opacity-90">{req.blocker_note}</p>}
      {req.blocker_review_on && <p className="text-xs opacity-90">Review on {new Date(req.blocker_review_on).toLocaleDateString()}</p>}
    </div>
  )
}

function QueueTransparency({ req }: { req: any }) {
  if (!req.queue_reason && !req.blocker_label && !req.queue_position) return null

  const bandStyles = {
    up_next: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
    near_front: 'bg-blue-500/15 text-blue-300 border border-blue-500/30',
    in_pack: 'bg-amber-500/15 text-amber-300 border border-amber-500/30',
    long_tail: 'bg-slate-700 text-slate-300 border border-slate-600',
  } as const

  const bandLabels = {
    up_next: 'Up next',
    near_front: 'Near front',
    in_pack: 'Middle pack',
    long_tail: 'Later queue',
  } as const

  const band = req.queue_band && bandLabels[req.queue_band as keyof typeof bandLabels]
    ? req.queue_band as keyof typeof bandLabels
    : 'long_tail'

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium ${bandStyles[band]}`}>
          {bandLabels[band]}
        </span>
        {req.queue_position && req.queue_size && (
          <span className="text-xs text-slate-400">Queue #{req.queue_position} of {req.queue_size}</span>
        )}
      </div>
      {req.queue_reason && <p className="text-xs text-slate-300">{req.queue_reason}</p>}
      {req.blocker_label && <p className="text-xs text-slate-500">{req.blocker_label}</p>}
    </div>
  )
}

export default function MyRequestsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [expandedComments, setExpandedComments] = useState<Set<number>>(new Set())
  const [expandedTimeline, setExpandedTimeline] = useState<Set<number>>(new Set())
  const queryClient = useQueryClient()

  const toggleComments = (id: number) => {
    setExpandedComments((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleTimeline = (id: number) => {
    setExpandedTimeline((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const { data, isLoading } = useQuery({
    queryKey: ['myRequests', statusFilter],
    queryFn: () => getMyRequests(1, 100, statusFilter || undefined),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: number) => deleteRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['myRequests'] }),
  })

  const requests = data?.items || []

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white">My Requests</h2>
        <Link
          to="/search"
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          + New Request
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        {['', 'pending', 'approved', 'fulfilled', 'denied'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded text-sm transition-colors ${
              statusFilter === s
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-slate-400">Loading...</p>}

      {!isLoading && requests.length === 0 && (
        <p className="text-slate-500 text-center py-12">No requests yet. Search for media to make a request.</p>
      )}

      {/* Mobile card view */}
      {!isLoading && requests.length > 0 && (
        <div className="md:hidden space-y-3">
          {requests.map((req: any) => (
            <div key={req.id} id={`request-${req.id}`} className="bg-slate-800 rounded-lg p-4 space-y-2 scroll-mt-24">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-white">{req.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {req.media_type.toUpperCase()} &middot; {new Date(req.created_at).toLocaleDateString()}
                  </p>
                </div>
                <RequestBadge status={req.status} />
              </div>
              {req.admin_note && (
                <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">{req.admin_note}</p>
              )}
              <p className="text-xs text-slate-500">{req.supporter_count || 1} supporter{(req.supporter_count || 1) === 1 ? '' : 's'}</p>
              <QueueTransparency req={req} />
              <BlockerSnapshot req={req} />
              <PromiseSnapshot req={req} />
              <NextStepHint req={req} />
              <EtaHint req={req} />
              <div className="flex items-center gap-3 flex-wrap">
                {req.watch_url && (
                  <WatchNowButton url={req.watch_url} />
                )}
                {req.status === 'fulfilled' && !req.watch_url && (
                  <span className="text-xs text-slate-500 italic">Link pending</span>
                )}
                {req.status === 'pending' && (
                  <button
                    onClick={() => cancelMutation.mutate(req.id)}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    {req.is_owner ? 'Cancel request' : 'Remove support'}
                  </button>
                )}
                <button
                  onClick={() => toggleTimeline(req.id)}
                  className="text-xs text-slate-400 hover:text-cyan-400 transition-colors"
                >
                  {expandedTimeline.has(req.id) ? '🕒 Hide timeline' : '🕒 Timeline'}
                </button>
                <button
                  onClick={() => toggleComments(req.id)}
                  className="text-xs text-slate-400 hover:text-blue-400 transition-colors"
                >
                  {expandedComments.has(req.id) ? '▲ Hide comments' : '💬 Comments'}
                </button>
              </div>
              {expandedTimeline.has(req.id) && <RequestTimeline requestId={req.id} />}
              {expandedComments.has(req.id) && <RequestComments requestId={req.id} />}
            </div>
          ))}
        </div>
      )}

      {/* Desktop table view */}
      {!isLoading && requests.length > 0 && (
        <div className="hidden md:block bg-slate-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Supporters</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Next Step</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Note</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {requests.map((req: any) => (
                  <>
                    <tr id={`request-${req.id}`} key={req.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 scroll-mt-24">
                      <td className="px-4 py-3 text-white text-sm">{req.title}</td>
                      <td className="px-4 py-3 text-slate-400 text-sm uppercase">{req.media_type}</td>
                      <td className="px-4 py-3">
                        <RequestBadge status={req.status} />
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-sm">
                        {new Date(req.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-sm">{req.supporter_count || 1}</td>
                      <td className="px-4 py-3 text-slate-300 text-xs">
                        {req.next_step_label ? (
                          <div>
                            <div>{req.next_step_label}</div>
                            <div className="text-slate-500 mt-0.5">
                              {req.queue_position && req.queue_size ? `Queue #${req.queue_position}/${req.queue_size}` : 'Queue details unavailable'}
                            </div>
                            {req.queue_reason && <div className="text-slate-400 mt-0.5">{req.queue_reason}</div>}
                            {req.blocker_label && <div className="text-slate-500 mt-0.5">{req.blocker_label}</div>}
                            {req.blocker_reason && (
                              <div className={`mt-1 rounded border px-2 py-1 ${req.blocker_is_overdue ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                                <div>{req.blocker_reason}</div>
                                {req.blocker_note && <div className="text-[11px] opacity-80 mt-0.5">{req.blocker_note}</div>}
                                {req.blocker_review_on && <div className="text-[11px] opacity-80 mt-0.5">Review on {new Date(req.blocker_review_on).toLocaleDateString()}</div>}
                              </div>
                            )}
                            {req.promise_summary && <div className="text-slate-300 mt-1">{req.promise_summary}</div>}
                            {req.benchmark_label && <div className="text-slate-500 mt-0.5">Normal: {req.benchmark_label}</div>}
                            {req.follow_up_label && (
                              <div className="text-slate-400 mt-0.5">
                                {req.follow_up_label}
                                {req.follow_up_by ? ` (${new Date(req.follow_up_by).toLocaleDateString()})` : ''}
                              </div>
                            )}
                            {req.eta_label && (
                              <div className="text-emerald-300 mt-0.5">
                                ETA: {req.eta_label}
                                {req.eta_confidence ? ` (${req.eta_confidence})` : ''}
                              </div>
                            )}
                          </div>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-sm">{req.admin_note || '-'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          {req.watch_url ? (
                            <WatchNowButton url={req.watch_url} />
                          ) : req.status === 'fulfilled' ? (
                            <span className="text-xs text-slate-500 italic">Link pending</span>
                          ) : req.status === 'pending' ? (
                            <button
                              onClick={() => cancelMutation.mutate(req.id)}
                              className="text-red-400 hover:text-red-300 text-sm"
                            >
                              {req.is_owner ? 'Cancel request' : 'Remove support'}
                            </button>
                          ) : null}
                          <button
                            onClick={() => toggleTimeline(req.id)}
                            className="text-xs text-slate-400 hover:text-cyan-400 transition-colors"
                          >
                            {expandedTimeline.has(req.id) ? '🕒 Hide' : '🕒'}
                          </button>
                          <button
                            onClick={() => toggleComments(req.id)}
                            className="text-xs text-slate-400 hover:text-blue-400 transition-colors"
                          >
                            {expandedComments.has(req.id) ? '▲ Hide' : '💬'}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedComments.has(req.id) && (
                      <tr key={`comments-${req.id}`} className="border-b border-slate-700/50 bg-slate-800/50">
                        <td colSpan={8} className="px-4 py-2">
                          <RequestComments requestId={req.id} />
                        </td>
                      </tr>
                    )}
                    {expandedTimeline.has(req.id) && (
                      <tr key={`timeline-${req.id}`} className="border-b border-slate-700/50 bg-slate-800/50">
                        <td colSpan={8} className="px-4 py-2">
                          <RequestTimeline requestId={req.id} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
