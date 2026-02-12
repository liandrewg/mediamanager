const statusStyles: Record<string, string> = {
  pending: 'bg-yellow-600 text-yellow-100',
  approved: 'bg-blue-600 text-blue-100',
  denied: 'bg-red-600 text-red-100',
  fulfilled: 'bg-green-600 text-green-100',
}

export default function RequestBadge({ status }: { status: string }) {
  return (
    <span
      className={`text-xs px-2 py-1 rounded capitalize ${statusStyles[status] || 'bg-slate-600 text-slate-100'}`}
    >
      {status}
    </span>
  )
}
