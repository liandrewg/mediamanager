import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { getLibraryMovies, getLibraryTvShows } from '../api/jellyfin'
import { updateJellyfinLink, type RequestRecord } from '../api/requests'

type SearchResult = {
  jellyfin_id: string
  title: string
  year?: number | null
  poster_url?: string | null
}

function LinkSearchCard({
  request,
  onLinked,
}: {
  request: RequestRecord
  onLinked: () => void
}) {
  const [query, setQuery] = useState(request.title)
  const [results, setResults] = useState<SearchResult[]>([])
  const [searched, setSearched] = useState(false)

  const searchMutation = useMutation({
    mutationFn: async () => {
      const search = query.trim() || request.title
      const response = request.media_type === 'movie'
        ? await getLibraryMovies(1, 8, search)
        : await getLibraryTvShows(1, 8, search)
      return response.items as SearchResult[]
    },
    onSuccess: (items) => {
      setResults(items)
      setSearched(true)
    },
  })

  const linkMutation = useMutation({
    mutationFn: (jellyfinItemId: string) => updateJellyfinLink(request.id, jellyfinItemId),
    onSuccess: () => {
      onLinked()
    },
  })

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-white">{request.title}</p>
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
              Missing Watch link
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {request.username} · {request.media_type.toUpperCase()} · fulfilled {new Date(request.updated_at).toLocaleDateString()}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Request #{request.id} · {request.supporter_count} supporter{request.supporter_count === 1 ? '' : 's'}
          </p>
        </div>
        <div className="text-xs text-slate-500">
          Link it once so requesters can jump straight into Jellyfin instead of asking where it went.
        </div>
      </div>

      <div className="flex flex-col gap-2 md:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search library by title"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-500"
        />
        <button
          onClick={() => searchMutation.mutate()}
          disabled={searchMutation.isPending}
          className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {searchMutation.isPending ? 'Searching...' : 'Find matches'}
        </button>
      </div>

      {searchMutation.isError && (
        <p className="text-xs text-red-400">Library search failed. Jellyfin may be down or unreachable.</p>
      )}

      {searched && results.length === 0 && !searchMutation.isPending && (
        <p className="text-xs text-slate-400">No matches found. Try a shorter title or a franchise keyword.</p>
      )}

      {results.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {results.map((item) => (
            <div key={item.jellyfin_id} className="flex gap-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="h-20 w-14 flex-shrink-0 overflow-hidden rounded bg-slate-800">
                {item.poster_url ? (
                  <img src={item.poster_url} alt={item.title} className="h-full w-full object-cover" loading="lazy" />
                ) : (
                  <div className="flex h-full items-center justify-center text-[10px] text-slate-500">No poster</div>
                )}
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <div>
                  <p className="truncate text-sm font-medium text-white">{item.title}</p>
                  <p className="text-xs text-slate-400">{item.year || 'Year unknown'} · {item.jellyfin_id}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => linkMutation.mutate(item.jellyfin_id)}
                    disabled={linkMutation.isPending}
                    className="rounded bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {linkMutation.isPending && linkMutation.variables === item.jellyfin_id ? 'Linking...' : 'Use this match'}
                  </button>
                  <a
                    href={item.poster_url || '#'}
                    target="_blank"
                    rel="noreferrer"
                    className={`rounded border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 ${item.poster_url ? 'hover:bg-slate-800' : 'pointer-events-none opacity-40'}`}
                  >
                    Poster
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {linkMutation.isError && (
        <p className="text-xs text-red-400">Failed to save Jellyfin link.</p>
      )}
    </div>
  )
}

export default function FulfillmentLinkRecoveryPanel({
  items,
  onLinked,
}: {
  items: RequestRecord[]
  onLinked: () => void
}) {
  const recoverable = items.filter((item) => item.status === 'fulfilled' && !item.watch_url && (item.media_type === 'movie' || item.media_type === 'tv'))

  if (recoverable.length === 0) return null

  return (
    <div className="mb-6 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-white font-semibold">Watch Link Recovery</h3>
          <p className="text-sm text-slate-300">Close the last mile on fulfilled requests so the house can actually hit Play.</p>
        </div>
        <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300">
          {recoverable.length} missing link{recoverable.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {recoverable.slice(0, 6).map((item) => (
          <LinkSearchCard key={item.id} request={item} onLinked={onLinked} />
        ))}
      </div>
    </div>
  )
}
