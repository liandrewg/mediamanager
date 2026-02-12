import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLibraryMovies, getLibraryTvShows } from '../api/jellyfin'
import { useDebounce } from '../hooks/useDebounce'
import SearchBar from '../components/SearchBar'

export default function LibraryPage() {
  const [tab, setTab] = useState<'movies' | 'tv'>('movies')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebounce(search, 400)

  const { data, isLoading, error } = useQuery({
    queryKey: ['library', tab, debouncedSearch, page],
    queryFn: () =>
      tab === 'movies'
        ? getLibraryMovies(page, 50, debouncedSearch || undefined)
        : getLibraryTvShows(page, 50, debouncedSearch || undefined),
  })

  const items = data?.items || []
  const total = data?.total || 0

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-6">Library</h2>

      <div className="flex gap-2 mb-6">
        <button
          onClick={() => { setTab('movies'); setPage(1) }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'movies' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          Movies
        </button>
        <button
          onClick={() => { setTab('tv'); setPage(1) }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === 'tv' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          TV Shows
        </button>
      </div>

      <SearchBar
        value={search}
        onChange={(v) => { setSearch(v); setPage(1) }}
        placeholder={`Search ${tab === 'movies' ? 'movies' : 'TV shows'} in library...`}
      />

      {error && <p className="text-red-400 mt-4">Failed to load library. Is Jellyfin running?</p>}

      {isLoading && <p className="text-slate-400 text-center mt-8">Loading...</p>}

      {!isLoading && (
        <div className="mt-6">
          <p className="text-sm text-slate-400 mb-4">{total} items</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {items.map((item: any) => (
              <div key={item.jellyfin_id} className="bg-slate-800 rounded-lg overflow-hidden">
                <div className="aspect-[2/3] bg-slate-700">
                  {item.poster_url ? (
                    <img
                      src={item.poster_url}
                      alt={item.title}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-slate-500 text-sm">
                      No Poster
                    </div>
                  )}
                </div>
                <div className="p-3">
                  <h3 className="text-sm font-medium text-white truncate">{item.title}</h3>
                  {item.year && <span className="text-xs text-slate-400">{item.year}</span>}
                </div>
              </div>
            ))}
          </div>

          {total > 50 && (
            <div className="flex justify-center gap-4 mt-8">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded text-sm text-white"
              >
                Previous
              </button>
              <span className="text-slate-400 self-center text-sm">Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={items.length < 50}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded text-sm text-white"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
