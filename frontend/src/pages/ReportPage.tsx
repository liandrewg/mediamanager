import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { createReport, getMyReports } from '../api/backlog'
import RequestBadge from '../components/RequestBadge'

const statusLabels: Record<string, string> = {
  reported: 'Reported',
  triaged: 'Triaged',
  in_progress: 'In Progress',
  ready_for_test: 'Ready for Test',
  resolved: 'Resolved',
  wont_fix: "Won't Fix",
}

export default function ReportPage() {
  const [type, setType] = useState<'bug' | 'feature'>('bug')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const queryClient = useQueryClient()

  const { data: myReports } = useQuery({
    queryKey: ['myReports'],
    queryFn: getMyReports,
  })

  const submitMutation = useMutation({
    mutationFn: () => createReport({ type, title, description: description || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['myReports'] })
      setTitle('')
      setDescription('')
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    submitMutation.mutate()
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-white mb-6">Report a Bug or Request a Feature</h2>

      {/* Submit Form */}
      <div className="bg-slate-800 rounded-lg p-6 mb-8">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setType('bug')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                type === 'bug' ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Bug Report
            </button>
            <button
              type="button"
              onClick={() => setType('feature')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                type === 'feature' ? 'bg-purple-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Feature Request
            </button>
          </div>

          <div>
            <label className="block text-sm text-slate-300 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder={type === 'bug' ? 'Brief description of the bug...' : 'What feature would you like?'}
              className="w-full px-4 py-2.5 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-300 mb-1">Details (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder={
                type === 'bug'
                  ? 'Steps to reproduce, what you expected vs what happened...'
                  : 'Describe the feature, why it would be useful...'
              }
              className="w-full px-4 py-2.5 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>

          <div className="flex items-center gap-4">
            <button
              type="submit"
              disabled={submitMutation.isPending || !title.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
            >
              {submitMutation.isPending ? 'Submitting...' : 'Submit'}
            </button>
            {submitMutation.isSuccess && (
              <span className="text-green-400 text-sm">Submitted! Thank you for your feedback.</span>
            )}
            {submitMutation.isError && (
              <span className="text-red-400 text-sm">Failed to submit. Please try again.</span>
            )}
          </div>
        </form>
      </div>

      {/* My Reports */}
      {myReports && myReports.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-white mb-3">Your Submissions</h3>

          {/* Mobile card view */}
          <div className="md:hidden space-y-3">
            {myReports.map((item: any) => (
              <div key={item.id} className="bg-slate-800 rounded-lg p-4 space-y-2">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">{item.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {new Date(item.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                        item.type === 'bug'
                          ? 'bg-red-600/30 text-red-300'
                          : 'bg-purple-600/30 text-purple-300'
                      }`}
                    >
                      {item.type}
                    </span>
                    <span className="text-xs text-slate-300">{statusLabels[item.status] || item.status}</span>
                  </div>
                </div>
                {item.admin_note && (
                  <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">{item.admin_note}</p>
                )}
              </div>
            ))}
          </div>

          {/* Desktop table view */}
          <div className="hidden md:block bg-slate-800 rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                  <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Admin Note</th>
                </tr>
              </thead>
              <tbody>
                {myReports.map((item: any) => (
                  <tr key={item.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs px-2 py-1 rounded font-medium ${
                          item.type === 'bug'
                            ? 'bg-red-600/30 text-red-300'
                            : 'bg-purple-600/30 text-purple-300'
                        }`}
                      >
                        {item.type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-white text-sm">{item.title}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-slate-300">{statusLabels[item.status] || item.status}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-sm">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-sm">{item.admin_note || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
