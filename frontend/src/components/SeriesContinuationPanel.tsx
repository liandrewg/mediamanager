import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type ContinuationCandidate,
  dismissSeriesContinuation,
  getSeriesContinuationRadar,
  queueSeriesContinuation,
} from '../api/seriesContinuation'

const POSTER_BASE = 'https://image.tmdb.org/t/p/w154'

function formatDate(value: string | null | undefined): string {
  if (!value) return 'unknown'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleDateString()
}

function CandidateCard({ candidate, onAction }: { candidate: ContinuationCandidate; onAction: () => void }) {
  const queueMutation = useMutation({
    mutationFn: () => queueSeriesContinuation(candidate.tmdb_id),
    onSuccess: () => onAction(),
  })

  const dismissMutation = useMutation({
    mutationFn: () => dismissSeriesContinuation(candidate.tmdb_id),
    onSuccess: () => onAction(),
  })

  const tmdbStatus = candidate.tmdb_status ?? 'unknown'
  const error = (queueMutation.error as Error | null) || (dismissMutation.error as Error | null)

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4">
      <div className="flex gap-3">
        <div className="h-24 w-16 flex-shrink-0 overflow-hidden rounded bg-slate-800">
          {candidate.poster_path ? (
            <img
              src={`${POSTER_BASE}${candidate.poster_path}`}
              alt={candidate.title}
              loading="lazy"
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-[10px] text-slate-500">No poster</div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-white">{candidate.title}</p>
            <span className="rounded-full bg-purple-500/15 px-2 py-0.5 text-[11px] font-medium text-purple-300">
              +{candidate.new_seasons} season{candidate.new_seasons === 1 ? '' : 's'}
            </span>
            <span className="rounded-full bg-slate-700/60 px-2 py-0.5 text-[11px] font-medium text-slate-300">
              {tmdbStatus}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Fulfilled {formatDate(candidate.fulfilled_at)} · last new episode {formatDate(candidate.last_air_date)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Through season {candidate.dismissed_through} of {candidate.last_aired_seasons}
            {candidate.household_supporters > 0
              ? ` · ${candidate.household_supporters} household supporter${candidate.household_supporters === 1 ? '' : 's'}`
              : ''}
            {candidate.original_request_id ? ` · originally request #${candidate.original_request_id}` : ''}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => queueMutation.mutate()}
          disabled={queueMutation.isPending || dismissMutation.isPending}
          className="rounded bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {queueMutation.isPending ? 'Queueing...' : 'Queue follow-up'}
        </button>
        <button
          onClick={() => dismissMutation.mutate()}
          disabled={queueMutation.isPending || dismissMutation.isPending}
          className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
        >
          {dismissMutation.isPending ? 'Dismissing...' : 'Skip'}
        </button>
        <a
          href={`https://www.themoviedb.org/tv/${candidate.tmdb_id}`}
          target="_blank"
          rel="noreferrer"
          className="rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
        >
          TMDB
        </a>
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-400">
          {error.message || 'Action failed'}
        </p>
      )}
    </div>
  )
}

export default function SeriesContinuationPanel() {
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  const radarQuery = useQuery({
    queryKey: ['admin', 'series-continuation'],
    queryFn: () => getSeriesContinuationRadar(false),
    staleTime: 60_000,
  })

  const refreshMutation = useMutation({
    mutationFn: async () => {
      setRefreshing(true)
      try {
        return await getSeriesContinuationRadar(true)
      } finally {
        setRefreshing(false)
      }
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['admin', 'series-continuation'], data)
    },
  })

  const data = radarQuery.data
  const candidates = data?.candidates ?? []
  const refreshSummary = refreshMutation.data?.refresh

  return (
    <div className="mb-6 rounded-xl border border-purple-500/30 bg-purple-500/5 p-4 space-y-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-white font-semibold">Series Continuation Radar</h3>
          <p className="text-sm text-slate-300">
            Fulfilled TV shows with new seasons since last delivery. Queue the follow-up before someone DMs about it.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data ? (
            <span className="rounded-full bg-purple-500/15 px-2.5 py-1 text-xs font-medium text-purple-300">
              {candidates.length} pending
            </span>
          ) : null}
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshing}
            className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {refreshing ? 'Checking TMDB...' : 'Refresh from TMDB'}
          </button>
        </div>
      </div>

      {refreshSummary && (
        <p className="text-xs text-slate-400">
          Checked {refreshSummary.checked} title{refreshSummary.checked === 1 ? '' : 's'} ·{' '}
          {refreshSummary.candidates} now on radar · {refreshSummary.skipped_recent} skipped (fresh) ·{' '}
          {refreshSummary.errors} TMDB error{refreshSummary.errors === 1 ? '' : 's'}.
        </p>
      )}

      {radarQuery.isLoading && <p className="text-sm text-slate-400">Loading radar...</p>}

      {radarQuery.isError && (
        <p className="text-sm text-red-400">Couldn't load continuation radar.</p>
      )}

      {!radarQuery.isLoading && !radarQuery.isError && candidates.length === 0 && (
        <p className="text-sm text-slate-400">
          Nothing to chase. Hit "Refresh from TMDB" to re-check fulfilled TV shows.
        </p>
      )}

      {candidates.length > 0 && (
        <div className="grid gap-3 xl:grid-cols-2">
          {candidates.map((candidate) => (
            <CandidateCard
              key={candidate.tmdb_id}
              candidate={candidate}
              onAction={() => radarQuery.refetch()}
            />
          ))}
        </div>
      )}
    </div>
  )
}
