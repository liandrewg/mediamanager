import { Link } from 'react-router-dom'
import RequestBadge from './RequestBadge'

interface Props {
  tmdbId: number
  mediaType: string
  title: string
  posterPath?: string | null
  releaseDate?: string | null
  voteAverage?: number | null
  existingRequest?: string | null
  alreadyInLibrary?: boolean
}

const TMDB_IMG = 'https://image.tmdb.org/t/p/w300'

export default function MediaCard({
  tmdbId,
  mediaType,
  title,
  posterPath,
  releaseDate,
  voteAverage,
  existingRequest,
  alreadyInLibrary,
}: Props) {
  const year = releaseDate ? releaseDate.split('-')[0] : null

  return (
    <Link
      to={`/${mediaType}/${tmdbId}`}
      className="group bg-slate-800 rounded-lg overflow-hidden hover:ring-2 hover:ring-blue-500 transition-all"
    >
      <div className="aspect-[2/3] bg-slate-700 relative">
        {posterPath ? (
          <img
            src={`${TMDB_IMG}${posterPath}`}
            alt={title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-500 text-sm">
            No Poster
          </div>
        )}
        {(existingRequest || alreadyInLibrary) && (
          <div className="absolute top-2 right-2">
            {alreadyInLibrary ? (
              <span className="bg-green-600 text-white text-xs px-2 py-1 rounded">
                In Library
              </span>
            ) : (
              existingRequest && <RequestBadge status={existingRequest} />
            )}
          </div>
        )}
      </div>
      <div className="p-3">
        <h3 className="text-sm font-medium text-white truncate group-hover:text-blue-400 transition-colors">
          {title}
        </h3>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-slate-400">{year}</span>
          {voteAverage != null && voteAverage > 0 && (
            <span className="text-xs text-yellow-400">{voteAverage.toFixed(1)}</span>
          )}
        </div>
        <span className="text-xs text-slate-500 uppercase">{mediaType}</span>
      </div>
    </Link>
  )
}
