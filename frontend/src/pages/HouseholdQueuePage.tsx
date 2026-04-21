import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import StatsCard from '../components/StatsCard'
import RequestBadge from '../components/RequestBadge'
import { getHouseholdQueue, type RequestRecord } from '../api/requests'

function QueueChip({ req }: { req: RequestRecord }) {
  if (!req.queue_reason && !req.queue_position) return null

  const labelMap = {
    up_next: 'Up next',
    near_front: 'Near front',
    in_pack: 'Middle pack',
    long_tail: 'Later queue',
  } as const

  const toneMap = {
    up_next: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    near_front: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
    in_pack: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    long_tail: 'border-slate-600 bg-slate-800/80 text-slate-300',
  } as const

  const band = req.queue_band && req.queue_band in labelMap ? req.queue_band : 'long_tail'

  return (
    <div className={`rounded-lg border px-3 py-2 space-y-1 ${toneMap[band as keyof typeof toneMap]}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wide">{labelMap[band as keyof typeof labelMap]}</span>
        {req.queue_position && req.queue_size && <span>Queue #{req.queue_position} of {req.queue_size}</span>}
      </div>
      {req.queue_reason && <p className="text-xs opacity-90">{req.queue_reason}</p>}
      {req.blocker_label && <p className="text-xs opacity-75">{req.blocker_label}</p>}
    </div>
  )
}

function PromiseChip({ req }: { req: RequestRecord }) {
  if (!req.promise_summary && !req.follow_up_label) return null

  const toneMap = {
    ahead: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    on_track: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200',
    at_risk: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    breached: 'border-red-500/30 bg-red-500/10 text-red-200',
    done: 'border-slate-600 bg-slate-800/80 text-slate-300',
  } as const

  const labelMap = {
    ahead: 'Ahead of normal',
    on_track: 'On track',
    at_risk: 'Needs eyes soon',
    breached: 'Past household target',
    done: 'Closed',
  } as const

  const status = req.promise_status && req.promise_status in toneMap ? req.promise_status : 'on_track'

  return (
    <div className={`rounded-lg border px-3 py-2 space-y-1 ${toneMap[status as keyof typeof toneMap]}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide">{labelMap[status as keyof typeof labelMap]}</p>
      {req.promise_summary && <p className="text-xs">{req.promise_summary}</p>}
      {req.follow_up_label && (
        <p className="text-xs opacity-90">
          {req.follow_up_label}
          {req.follow_up_by ? ` (${new Date(req.follow_up_by).toLocaleDateString()})` : ''}
        </p>
      )}
    </div>
  )
}

export default function HouseholdQueuePage() {
  const [status, setStatus] = useState<'open' | 'all' | 'pending' | 'approved'>('open')
  const [mediaType, setMediaType] = useState<'all' | 'movie' | 'tv' | 'book'>('all')
  const [sort, setSort] = useState<'priority' | 'supporters' | 'newest' | 'oldest'>('priority')
  const [query, setQuery] = useState('')

  const trimmedQuery = useMemo(() => query.trim(), [query])

  const { data, isLoading } = useQuery({
    queryKey: ['householdQueue', status, mediaType, sort, trimmedQuery],
    queryFn: () => getHouseholdQueue({
      status,
      mediaType: mediaType === 'all' ? undefined : mediaType,
      sort,
      query: trimmedQuery || undefined,
      limit: 40,
    }),
  })

  const items = data?.items || []
  const summary = data?.summary

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Household Queue</h2>
          <p className="text-slate-400 max-w-3xl">See what the house is already waiting on before another DM gets sent into the void.</p>
        </div>
        <Link to="/search" className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500">
          Search and add support
        </Link>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatsCard label="Open Requests" value={summary.open_total} />
          <StatsCard label="Approved" value={summary.approved} />
          <StatsCard label="Pending" value={summary.pending} />
          <StatsCard label="Supporters" value={summary.total_supporters} />
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search queued titles"
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none ring-0 placeholder:text-slate-500"
          />
          <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white">
            <option value="open">Open only</option>
            <option value="approved">Approved only</option>
            <option value="pending">Pending only</option>
            <option value="all">Everything</option>
          </select>
          <select value={mediaType} onChange={(event) => setMediaType(event.target.value as typeof mediaType)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white">
            <option value="all">All media</option>
            <option value="movie">Movies</option>
            <option value="tv">TV</option>
            <option value="book">Books</option>
          </select>
          <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white">
            <option value="priority">Priority</option>
            <option value="supporters">Most supporters</option>
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
          </select>
        </div>
      </div>

      {isLoading && <p className="text-slate-400">Loading queue…</p>}

      {!isLoading && items.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-8 text-center text-slate-400">
          Nothing matched. Either the queue is clear, or the filter is being dramatic.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((req) => (
          <div key={req.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-lg font-semibold text-white">{req.title}</h3>
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-400">{req.media_type}</span>
                </div>
                <p className="text-sm text-slate-400">
                  Requested by {req.username}, {req.supporter_count} supporter{req.supporter_count === 1 ? '' : 's'}
                </p>
              </div>
              <RequestBadge status={req.status} />
            </div>

            <QueueChip req={req} />
            <PromiseChip req={req} />

            {req.next_step_label && (
              <p className="text-sm text-cyan-300">
                Next: {req.next_step_label}
                {req.next_step_by ? ` (${new Date(req.next_step_by).toLocaleDateString()})` : ''}
              </p>
            )}

            {req.benchmark_label && <p className="text-xs text-slate-400">Normal: {req.benchmark_label}</p>}

            <div className="flex flex-wrap gap-3 text-xs text-slate-500">
              <span>Opened {new Date(req.created_at).toLocaleDateString()}</span>
              {req.user_supporting ? <span className="text-emerald-300">You already support this</span> : <span>Use Search to add your support</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
