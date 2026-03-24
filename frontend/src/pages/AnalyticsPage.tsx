import { useQuery } from '@tanstack/react-query'
import { getAnalytics } from '../api/requests'

// ── Types ──────────────────────────────────────────────────────────────────

interface AnalyticsData {
  total_requests_all_time: number
  fulfilled_all_time: number
  fulfillment_rate: number
  avg_lead_time_days: number | null
  median_lead_time_days: number | null
  p90_lead_time_days: number | null
  open_count: number
  pending_count: number
  approved_count: number
  denied_count: number
  escalated_count: number
  oldest_open_days: number
  top_requesters: { username: string; count: number }[]
  by_media_type: { media_type: string; total: number; fulfilled: number }[]
  monthly_volume: { month: string; submitted: number; fulfilled: number }[]
  weekly_throughput: { week: string; fulfilled: number }[]
  total_supporters_ever: number
  avg_supporters_per_request: number
}

// ── Small helpers ──────────────────────────────────────────────────────────

function KpiCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-slate-800 rounded-xl p-5 flex flex-col gap-1">
      <span className="text-xs text-slate-400 uppercase tracking-wide">{label}</span>
      <span className="text-2xl font-bold text-white">{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}

// ── SVG bar chart ──────────────────────────────────────────────────────────

interface BarSeries {
  value: number
  color: string
}

interface BarChartProps {
  labels: string[]
  series: BarSeries[][]   // series[barIndex][labelIndex]
  height?: number
}

function BarChart({ labels, series, height = 180 }: BarChartProps) {
  const W = 600
  const H = height
  const PADDING_LEFT = 32
  const PADDING_BOTTOM = 28
  const PADDING_TOP = 8
  const chartW = W - PADDING_LEFT
  const chartH = H - PADDING_BOTTOM - PADDING_TOP

  const allValues = series.flat().map((s) => s.value)
  const maxVal = Math.max(...allValues, 1)

  const numGroups = labels.length
  const groupW = chartW / Math.max(numGroups, 1)
  const barsPerGroup = series.length
  const barPad = groupW * 0.15
  const barW = (groupW - barPad * 2) / Math.max(barsPerGroup, 1)

  if (numGroups === 0) {
    return (
      <div className="flex items-center justify-center h-36 text-slate-500 text-sm">
        No data yet
      </div>
    )
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ minHeight: height }}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* y-axis line */}
      <line
        x1={PADDING_LEFT}
        y1={PADDING_TOP}
        x2={PADDING_LEFT}
        y2={PADDING_TOP + chartH}
        stroke="#475569"
        strokeWidth={1}
      />
      {/* x-axis line */}
      <line
        x1={PADDING_LEFT}
        y1={PADDING_TOP + chartH}
        x2={W}
        y2={PADDING_TOP + chartH}
        stroke="#475569"
        strokeWidth={1}
      />

      {/* Bars */}
      {labels.map((label, gi) => {
        const groupX = PADDING_LEFT + gi * groupW + barPad
        return (
          <g key={gi}>
            {series.map((ser, si) => {
              const val = ser[gi]?.value ?? 0
              const barH = (val / maxVal) * chartH
              const x = groupX + si * barW
              const y = PADDING_TOP + chartH - barH
              return (
                <g key={si}>
                  <rect
                    x={x}
                    y={y}
                    width={barW - 1}
                    height={barH}
                    fill={ser[gi]?.color ?? '#64748b'}
                    rx={2}
                  />
                  {val > 0 && barH > 14 && (
                    <text
                      x={x + (barW - 1) / 2}
                      y={y + 11}
                      textAnchor="middle"
                      fontSize={9}
                      fill="#e2e8f0"
                    >
                      {val}
                    </text>
                  )}
                </g>
              )
            })}
            {/* x label */}
            <text
              x={groupX + (groupW - barPad * 2) / 2}
              y={H - 6}
              textAnchor="middle"
              fontSize={9}
              fill="#94a3b8"
            >
              {label.length > 7 ? label.slice(2) : label}
            </text>
          </g>
        )
      })}

      {/* y-axis max label */}
      <text x={PADDING_LEFT - 2} y={PADDING_TOP + 8} textAnchor="end" fontSize={9} fill="#94a3b8">
        {maxVal}
      </text>
    </svg>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const { data, isLoading, isError } = useQuery<AnalyticsData>({
    queryKey: ['admin-analytics'],
    queryFn: getAnalytics,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="text-slate-400 text-center py-20">Loading analytics…</div>
    )
  }

  if (isError || !data) {
    return (
      <div className="text-red-400 text-center py-20">
        Failed to load analytics. Make sure you are an admin.
      </div>
    )
  }

  // Monthly chart data
  const monthLabels = data.monthly_volume.map((m) => m.month)
  const monthSeries: BarSeries[][] = [
    data.monthly_volume.map((m) => ({ value: m.submitted, color: '#64748b' })),
    data.monthly_volume.map((m) => ({ value: m.fulfilled, color: '#22c55e' })),
  ]

  // Weekly chart data
  const weekLabels = data.weekly_throughput.map((w) => w.week)
  const weekSeries: BarSeries[][] = [
    data.weekly_throughput.map((w) => ({ value: w.fulfilled, color: '#3b82f6' })),
  ]

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-white">Household Analytics</h1>

      {/* ── Row 1: Summary KPIs ── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          All-Time Summary
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Total Requests" value={data.total_requests_all_time} />
          <KpiCard label="Fulfilled" value={data.fulfilled_all_time} />
          <KpiCard
            label="Fulfillment Rate"
            value={`${data.fulfillment_rate}%`}
            sub={`${data.fulfilled_all_time} of ${data.total_requests_all_time}`}
          />
          <KpiCard
            label="Avg Lead Time"
            value={data.avg_lead_time_days !== null ? `${data.avg_lead_time_days}d` : '—'}
            sub="submitted → fulfilled"
          />
        </div>
      </section>

      {/* ── Row 2: Backlog pressure ── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Backlog Pressure
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KpiCard label="Open" value={data.open_count} sub="pending + approved" />
          <KpiCard label="Pending" value={data.pending_count} />
          <KpiCard label="Approved" value={data.approved_count} />
          <KpiCard label="Escalated" value={data.escalated_count} sub="high-demand flags" />
          <KpiCard label="Oldest Open" value={`${data.oldest_open_days}d`} sub="days since created" />
        </div>
      </section>

      {/* ── Lead Time Stats ── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Lead Time Distribution
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            label="Average Lead Time"
            value={data.avg_lead_time_days !== null ? `${data.avg_lead_time_days} days` : '—'}
          />
          <KpiCard
            label="Median Lead Time"
            value={data.median_lead_time_days !== null ? `${data.median_lead_time_days} days` : '—'}
          />
          <KpiCard
            label="P90 Lead Time"
            value={data.p90_lead_time_days !== null ? `${data.p90_lead_time_days} days` : '—'}
            sub="90th percentile"
          />
        </div>
      </section>

      {/* ── Monthly Volume Chart ── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Monthly Request Volume
          <span className="ml-2 text-slate-600 normal-case font-normal">
            (
            <span className="inline-block w-2 h-2 rounded-sm bg-slate-500 mr-1" />
            submitted
            <span className="inline-block w-2 h-2 rounded-sm bg-green-500 mx-1 ml-2" />
            fulfilled)
          </span>
        </h2>
        <div className="bg-slate-800 rounded-xl p-4">
          {data.monthly_volume.length === 0 ? (
            <div className="text-slate-500 text-sm text-center py-10">No data yet</div>
          ) : (
            <BarChart labels={monthLabels} series={monthSeries} height={200} />
          )}
        </div>
      </section>

      {/* ── Weekly Throughput Chart ── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Weekly Throughput
          <span className="ml-2 text-slate-600 normal-case font-normal">
            (
            <span className="inline-block w-2 h-2 rounded-sm bg-blue-500 mr-1" />
            fulfilled)
          </span>
        </h2>
        <div className="bg-slate-800 rounded-xl p-4">
          {data.weekly_throughput.length === 0 ? (
            <div className="text-slate-500 text-sm text-center py-10">No data yet</div>
          ) : (
            <BarChart labels={weekLabels} series={weekSeries} height={160} />
          )}
        </div>
      </section>

      {/* ── Bottom row: media type + top requesters + supporters ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Media Type Breakdown */}
        <section className="bg-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-4">
            By Media Type
          </h2>
          {data.by_media_type.length === 0 ? (
            <p className="text-slate-500 text-sm">No data yet</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs border-b border-slate-700">
                  <th className="text-left pb-2">Type</th>
                  <th className="text-right pb-2">Total</th>
                  <th className="text-right pb-2">Fulfilled</th>
                </tr>
              </thead>
              <tbody>
                {data.by_media_type.map((row) => (
                  <tr key={row.media_type} className="border-b border-slate-700/50">
                    <td className="py-2 capitalize text-white">{row.media_type}</td>
                    <td className="py-2 text-right text-slate-300">{row.total}</td>
                    <td className="py-2 text-right text-green-400">{row.fulfilled}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Top Requesters */}
        <section className="bg-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-4">
            Top Requesters
          </h2>
          {data.top_requesters.length === 0 ? (
            <p className="text-slate-500 text-sm">No data yet</p>
          ) : (
            <ol className="space-y-2">
              {data.top_requesters.map((r, i) => (
                <li key={r.username} className="flex items-center gap-3">
                  <span className="text-slate-500 text-xs w-4">{i + 1}.</span>
                  <span className="flex-1 text-white text-sm truncate">{r.username}</span>
                  <span className="text-slate-300 text-sm font-mono">{r.count}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        {/* Supporter Engagement */}
        <section className="bg-slate-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-4">
            Supporter Engagement
          </h2>
          <div className="space-y-4">
            <KpiCard label="Total Supporters Ever" value={data.total_supporters_ever} />
            <KpiCard
              label="Avg Supporters / Request"
              value={data.avg_supporters_per_request}
            />
          </div>
        </section>
      </div>
    </div>
  )
}
