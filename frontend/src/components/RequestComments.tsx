import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getComments, postComment, deleteComment, type Comment } from '../api/requests'
import { useAuth } from '../context/AuthContext'

interface Props {
  requestId: number
}

function formatDate(iso: string) {
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export default function RequestComments({ requestId }: Props) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: comments = [], isLoading } = useQuery<Comment[]>({
    queryKey: ['comments', requestId],
    queryFn: () => getComments(requestId),
  })

  const addMutation = useMutation({
    mutationFn: (body: string) => postComment(requestId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', requestId] })
      setText('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: number) => deleteComment(requestId, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', requestId] })
    },
  })

  // Scroll to bottom when comments load or change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [comments.length])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return
    addMutation.mutate(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      const trimmed = text.trim()
      if (trimmed) addMutation.mutate(trimmed)
    }
  }

  return (
    <div className="mt-4 border-t border-slate-700 pt-4">
      <h4 className="text-sm font-semibold text-slate-400 mb-3 flex items-center gap-2">
        <span>💬</span>
        <span>Comments {comments.length > 0 && `(${comments.length})`}</span>
      </h4>

      {isLoading && (
        <p className="text-xs text-slate-500 italic">Loading comments…</p>
      )}

      {!isLoading && comments.length === 0 && (
        <p className="text-xs text-slate-500 italic mb-3">No comments yet. Be the first!</p>
      )}

      {comments.length > 0 && (
        <div className="space-y-2 mb-3 max-h-60 overflow-y-auto pr-1">
          {comments.map((c) => {
            const isOwn = c.user_id === user?.id
            const canDelete = isOwn || user?.is_admin
            return (
              <div
                key={c.id}
                className={`rounded-lg px-3 py-2 text-sm group relative ${
                  c.is_admin
                    ? 'bg-blue-900/40 border border-blue-700/50'
                    : 'bg-slate-700/50'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="flex items-center gap-1.5">
                    <span className="font-medium text-slate-200 text-xs">{c.username}</span>
                    {c.is_admin && (
                      <span className="text-[10px] bg-blue-600/50 text-blue-200 px-1.5 py-0.5 rounded font-medium">
                        Admin
                      </span>
                    )}
                  </span>
                  <span className="text-[10px] text-slate-500 shrink-0">{formatDate(c.created_at)}</span>
                </div>
                <p className="text-slate-300 leading-relaxed whitespace-pre-wrap break-words">{c.body}</p>
                {canDelete && (
                  <button
                    onClick={() => deleteMutation.mutate(c.id)}
                    disabled={deleteMutation.isPending}
                    className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity text-[10px] text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-900/30"
                  >
                    ✕
                  </button>
                )}
              </div>
            )
          })}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Composer */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a comment… (⌘↵ to send)"
          rows={2}
          className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 resize-none focus:outline-none focus:border-blue-500 transition-colors"
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!text.trim() || addMutation.isPending}
            className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            {addMutation.isPending ? 'Sending…' : 'Send'}
          </button>
        </div>
        {addMutation.isError && (
          <p className="text-xs text-red-400">Failed to send. Try again.</p>
        )}
      </form>
    </div>
  )
}
