import { useQuery } from '@tanstack/react-query'
import { getRequestPreflight } from '../api/tmdb'
import type { RequestPreflight } from '../api/tmdb'

interface Props {
  mediaType: 'movie' | 'tv' | 'book'
  tmdbId: number
}

const VERDICT_STYLE: Record<string, { tone: string; icon: string }> = {
  watch_now: { tone: 'border-green-500/40 bg-green-500/10', icon: '✓' },
  recently_added: { tone: 'border-emerald-500/40 bg-emerald-500/10', icon: '🆕' },
  already_supporting: { tone: 'border-blue-500/40 bg-blue-500/10', icon: '👤' },
  join_queue: { tone: 'border-amber-500/40 bg-amber-500/10', icon: '👥' },
  fresh_request: { tone: 'border-slate-500/40 bg-slate-500/10', icon: '🚀' },
}

export default function PreflightCard({ mediaType, tmdbId }: Props) {
  const { data, isLoading, error } = useQuery<RequestPreflight>({
    queryKey: ['preflight', mediaType, tmdbId],
    queryFn: () => getRequestPreflight(mediaType, tmdbId),
    // The data only changes when admins move the request; cache aggressively.
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
        <p className="text-sm text-slate-400">Checking your library and request queue...</p>
      </div>
    )
  }

  if (error || !data) {
    // Soft-fail: if preflight can't load, the existing request button still works.
    return null
  }

  const { verdict, community_request, eta, recently_fulfilled } = data
  const style = VERDICT_STYLE[verdict.code] || VERDICT_STYLE.fresh_request

  return (
    <div
      className={`rounded-lg border p-4 ${style.tone}`}
      data-testid="preflight-card"
      data-verdict={verdict.code}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl leading-none mt-0.5" aria-hidden>
          {style.icon}
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-white">{verdict.headline}</h3>
          {verdict.detail && (
            <p className="text-xs text-slate-300 mt-1 leading-relaxed">{verdict.detail}</p>
          )}

          {/* Community context: supporters, queue position, ETA */}
          {community_request && (
            <ul className="mt-3 space-y-1 text-xs text-slate-300">
              <li>
                <span className="text-slate-400">Supporters:</span>{' '}
                {community_request.supporter_count}
              </li>
              {community_request.queue_position && community_request.queue_size && (
                <li>
                  <span className="text-slate-400">Queue position:</span>{' '}
                  {community_request.queue_position} of {community_request.queue_size}
                </li>
              )}
              <li>
                <span className="text-slate-400">Open for:</span> {community_request.days_open}d
              </li>
              {eta && (
                <li>
                  <span className="text-slate-400">ETA:</span> {eta.label}
                  {eta.confidence && (
                    <span className="text-slate-500"> ({eta.confidence})</span>
                  )}
                </li>
              )}
            </ul>
          )}

          {/* Recently-fulfilled hint with optional watch URL */}
          {recently_fulfilled && (
            <p className="mt-3 text-xs text-slate-300">
              Fulfilled {recently_fulfilled.age_days === 0
                ? 'today'
                : `${recently_fulfilled.age_days}d ago`}
              {recently_fulfilled.watch_url && (
                <>
                  {' '}
                  ·{' '}
                  <a
                    href={recently_fulfilled.watch_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-300 hover:text-emerald-200 underline"
                  >
                    Open in Jellyfin
                  </a>
                </>
              )}
            </p>
          )}

          {/* Watch-now CTA when in library */}
          {verdict.primary_action === 'watch' && verdict.primary_action_url && (
            <a
              href={verdict.primary_action_url}
              target="_blank"
              rel="noreferrer"
              className="inline-block mt-3 bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded-md text-sm font-medium transition-colors"
            >
              {verdict.primary_action_label || 'Watch now'}
            </a>
          )}
        </div>
      </div>
    </div>
  )
}
