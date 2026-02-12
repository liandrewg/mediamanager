interface Props {
  label: string
  value: number | string
}

export default function StatsCard({ label, value }: Props) {
  return (
    <div className="bg-slate-800 rounded-lg p-6">
      <p className="text-3xl font-bold text-white">{value}</p>
      <p className="text-sm text-slate-400 mt-1">{label}</p>
    </div>
  )
}
