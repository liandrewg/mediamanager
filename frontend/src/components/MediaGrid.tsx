import MediaCard from './MediaCard'

interface MediaItem {
  tmdb_id: number
  media_type: string
  title: string
  poster_path?: string | null
  release_date?: string | null
  vote_average?: number | null
  existing_request?: string | null
  already_in_library?: boolean
}

interface Props {
  items: MediaItem[]
}

export default function MediaGrid({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-slate-400 text-center py-12">No results found.</p>
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
      {items.map((item) => (
        <MediaCard
          key={`${item.media_type}-${item.tmdb_id}`}
          tmdbId={item.tmdb_id}
          mediaType={item.media_type}
          title={item.title}
          posterPath={item.poster_path}
          releaseDate={item.release_date}
          voteAverage={item.vote_average}
          existingRequest={item.existing_request}
          alreadyInLibrary={item.already_in_library}
        />
      ))}
    </div>
  )
}
