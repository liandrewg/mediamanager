import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMovieDetails, getTvDetails } from '../api/tmdb'
import { createRequest } from '../api/requests'
import RequestBadge from '../components/RequestBadge'
import Spinner from '../components/Spinner'

const TMDB_IMG = 'https://image.tmdb.org/t/p'

interface Props {
  mediaType: 'movie' | 'tv'
}

export default function MediaDetailPage({ mediaType }: Props) {
  const { tmdbId } = useParams()
  const queryClient = useQueryClient()
  const id = Number(tmdbId)

  const { data, isLoading, error } = useQuery({
    queryKey: [mediaType, id],
    queryFn: () => (mediaType === 'movie' ? getMovieDetails(id) : getTvDetails(id)),
  })

  const requestMutation = useMutation({
    mutationFn: () =>
      createRequest({
        tmdb_id: id,
        media_type: mediaType,
        title: data?.title || '',
        poster_path: data?.poster_path,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [mediaType, id] })
    },
  })

  if (isLoading) return <Spinner />
  if (error || !data) return <p className="text-red-400">Failed to load details.</p>

  const backdropUrl = data.backdrop_path ? `${TMDB_IMG}/w1280${data.backdrop_path}` : null
  const posterUrl = data.poster_path ? `${TMDB_IMG}/w300${data.poster_path}` : null
  const year = (data.release_date || data.first_air_date || '').split('-')[0]
  const canRequest = !data.existing_request && !data.already_in_library

  return (
    <div>
      {/* Backdrop */}
      {backdropUrl && (
        <div className="relative -mx-8 -mt-8 mb-8 h-72 overflow-hidden">
          <img src={backdropUrl} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-slate-900 to-transparent" />
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-8">
        {/* Poster */}
        <div className="flex-shrink-0 w-56">
          {posterUrl ? (
            <img src={posterUrl} alt={data.title} className="w-full rounded-lg shadow-lg" />
          ) : (
            <div className="w-full aspect-[2/3] bg-slate-700 rounded-lg flex items-center justify-center text-slate-400">
              No Poster
            </div>
          )}
        </div>

        {/* Details */}
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-white">
            {data.title} {year && <span className="text-slate-400 font-normal">({year})</span>}
          </h1>

          <div className="flex flex-wrap items-center gap-3 mt-3">
            {data.genres?.map((g: string) => (
              <span key={g} className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">
                {g}
              </span>
            ))}
            {data.runtime && <span className="text-sm text-slate-400">{data.runtime} min</span>}
            {data.number_of_seasons && (
              <span className="text-sm text-slate-400">
                {data.number_of_seasons} season{data.number_of_seasons !== 1 ? 's' : ''}
              </span>
            )}
            {data.vote_average != null && data.vote_average > 0 && (
              <span className="text-sm text-yellow-400">{data.vote_average.toFixed(1)} / 10</span>
            )}
          </div>

          {data.overview && <p className="mt-4 text-slate-300 leading-relaxed">{data.overview}</p>}

          {/* Action buttons */}
          <div className="mt-6 flex items-center gap-4">
            {data.already_in_library && (
              <span className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium">
                Already in Library
              </span>
            )}
            {data.existing_request && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-400">Request status:</span>
                <RequestBadge status={data.existing_request} />
              </div>
            )}
            {canRequest && (
              <button
                onClick={() => requestMutation.mutate()}
                disabled={requestMutation.isPending}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-6 py-2 rounded-lg font-medium transition-colors"
              >
                {requestMutation.isPending ? 'Requesting...' : 'Request'}
              </button>
            )}
            {requestMutation.isError && (
              <span className="text-red-400 text-sm">
                {(requestMutation.error as any)?.response?.data?.detail || 'Failed to submit request'}
              </span>
            )}
            {requestMutation.isSuccess && (
              <span className="text-green-400 text-sm">Request submitted!</span>
            )}
          </div>

          {/* Cast */}
          {data.cast && data.cast.length > 0 && (
            <div className="mt-8">
              <h3 className="text-lg font-semibold text-white mb-3">Cast</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                {data.cast.map((person: any, i: number) => (
                  <div key={i} className="text-center">
                    {person.profile_path ? (
                      <img
                        src={`${TMDB_IMG}/w185${person.profile_path}`}
                        alt={person.name}
                        className="w-full aspect-[2/3] object-cover rounded-lg"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full aspect-[2/3] bg-slate-700 rounded-lg flex items-center justify-center text-slate-500 text-xs">
                        No Photo
                      </div>
                    )}
                    <p className="text-sm text-white mt-1 truncate">{person.name}</p>
                    <p className="text-xs text-slate-400 truncate">{person.character}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
