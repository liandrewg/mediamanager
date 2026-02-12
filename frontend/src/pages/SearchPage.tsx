import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchMedia } from '../api/tmdb'
import { useDebounce } from '../hooks/useDebounce'
import SearchBar from '../components/SearchBar'
import MediaGrid from '../components/MediaGrid'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const debouncedQuery = useDebounce(query, 400)

  const { data, isLoading } = useQuery({
    queryKey: ['search', debouncedQuery, page],
    queryFn: () => searchMedia(debouncedQuery, page),
    enabled: debouncedQuery.length >= 2,
  })

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-6">Search</h2>
      <SearchBar value={query} onChange={(v) => { setQuery(v); setPage(1) }} />

      <div className="mt-8">
        {isLoading && debouncedQuery.length >= 2 && (
          <p className="text-slate-400 text-center">Searching...</p>
        )}
        {data && (
          <>
            <p className="text-sm text-slate-400 mb-4">
              {data.total_results} result{data.total_results !== 1 ? 's' : ''}
            </p>
            <MediaGrid items={data.results} />
            {data.total_pages > 1 && (
              <div className="flex justify-center gap-4 mt-8">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded text-sm text-white"
                >
                  Previous
                </button>
                <span className="text-slate-400 self-center text-sm">
                  Page {page} of {data.total_pages}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= data.total_pages}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded text-sm text-white"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
        {!isLoading && !data && debouncedQuery.length < 2 && (
          <p className="text-slate-500 text-center py-12">Type at least 2 characters to search</p>
        )}
      </div>
    </div>
  )
}
