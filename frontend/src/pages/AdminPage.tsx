import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getAllRequests,
  updateRequest,
  bulkUpdateRequests,
  getAdminStats,
  getAdminReplyPack,
  getRequesterDigestPack,
  getRequestReviewLoop,
  getUsers,
  updateUserRole,
  getHealthCheck,
  triggerJellyfinScan,
  getDuplicateRequestGroups,
  mergeDuplicateRequests,
  setRequestBlocker,
  clearRequestBlocker,
  getAnalytics,
  getSlaPolicy,
  updateSlaPolicy,
  applyRecommendedSlaPolicy,
  getSlaWorklist,
  bulkEscalateSlaRequests,
  simulateSlaPolicy,
  type AdminAnalytics,
  type AdminReplyPackItem,
  type DuplicateGroup,
  type RequestReviewLoopItem,
  type RequesterDigestPackItem,
  type SlaSimulationScenario,
} from '../api/requests'
import { getAllBacklog, updateBacklogItem, deleteBacklogItem, getBacklogStats } from '../api/backlog'
import { getTunnelStatus, startTunnel, stopTunnel } from '../api/tunnel'
import { useAuth } from '../context/AuthContext'
import RequestBadge from '../components/RequestBadge'
import StatsCard from '../components/StatsCard'
import RequestComments from '../components/RequestComments'
import FulfillmentLinkRecoveryPanel from '../components/FulfillmentLinkRecoveryPanel'

const COLUMNS = [
  { key: 'pending', label: 'Pending', color: 'border-yellow-500', bg: 'bg-yellow-500/10' },
  { key: 'approved', label: 'Approved', color: 'border-blue-500', bg: 'bg-blue-500/10' },
  { key: 'fulfilled', label: 'Fulfilled', color: 'border-green-500', bg: 'bg-green-500/10' },
  { key: 'denied', label: 'Denied', color: 'border-red-500', bg: 'bg-red-500/10' },
]

const TRANSITIONS: Record<string, { label: string; status: string; style: string }[]> = {
  pending: [
    { label: 'Approve', status: 'approved', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
    { label: 'Deny', status: 'denied', style: 'bg-red-600 hover:bg-red-700 text-white' },
  ],
  approved: [
    { label: 'Mark Fulfilled', status: 'fulfilled', style: 'bg-green-600 hover:bg-green-700 text-white' },
    { label: 'Back to Pending', status: 'pending', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
    { label: 'Deny', status: 'denied', style: 'bg-red-600 hover:bg-red-700 text-white' },
  ],
  fulfilled: [
    { label: 'Reopen', status: 'approved', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  denied: [
    { label: 'Reopen', status: 'pending', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
  ],
}

const BACKLOG_COLUMNS = [
  { key: 'reported', label: 'Reported', color: 'border-yellow-500', bg: 'bg-yellow-500/10' },
  { key: 'triaged', label: 'Triaged', color: 'border-blue-500', bg: 'bg-blue-500/10' },
  { key: 'in_progress', label: 'In Progress', color: 'border-purple-500', bg: 'bg-purple-500/10' },
  { key: 'ready_for_test', label: 'Ready for Test', color: 'border-cyan-500', bg: 'bg-cyan-500/10' },
  { key: 'resolved', label: 'Resolved', color: 'border-green-500', bg: 'bg-green-500/10' },
  { key: 'wont_fix', label: "Won't Fix", color: 'border-slate-500', bg: 'bg-slate-500/10' },
]

const BACKLOG_TRANSITIONS: Record<string, { label: string; status: string; style: string }[]> = {
  reported: [
    { label: 'Triage', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
    { label: "Won't Fix", status: 'wont_fix', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  triaged: [
    { label: 'Start Work', status: 'in_progress', style: 'bg-purple-600 hover:bg-purple-700 text-white' },
    { label: "Won't Fix", status: 'wont_fix', style: 'bg-slate-600 hover:bg-slate-500 text-white' },
  ],
  in_progress: [
    { label: 'Ready for Test', status: 'ready_for_test', style: 'bg-cyan-600 hover:bg-cyan-700 text-white' },
    { label: 'Back to Triaged', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
  ],
  ready_for_test: [
    { label: 'Resolve', status: 'resolved', style: 'bg-green-600 hover:bg-green-700 text-white' },
    { label: 'Back to In Progress', status: 'in_progress', style: 'bg-purple-600 hover:bg-purple-700 text-white' },
  ],
  resolved: [
    { label: 'Reopen', status: 'triaged', style: 'bg-blue-600 hover:bg-blue-700 text-white' },
  ],
  wont_fix: [
    { label: 'Reopen', status: 'reported', style: 'bg-yellow-600 hover:bg-yellow-700 text-white' },
  ],
}

const PRIORITY_STYLES: Record<string, string> = {
  low: 'bg-slate-600/30 text-slate-300',
  medium: 'bg-yellow-600/30 text-yellow-300',
  high: 'bg-orange-600/30 text-orange-300',
  critical: 'bg-red-600/30 text-red-300',
}

type Tab = 'requests' | 'duplicates' | 'sla' | 'backlog' | 'users' | 'tunnel' | 'health'
type DuplicateSelectionState = Record<string, { targetId: number; sourceIds: number[] }>

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('requests')
  const [view, setView] = useState<'board' | 'table'>('board')
  const [sortBy, setSortBy] = useState<'priority' | 'newest' | 'oldest' | 'supporters'>('priority')
  const [mediaTypeFilter, setMediaTypeFilter] = useState<'all' | 'movie' | 'tv' | 'book'>('all')
  const [ageFilter, setAgeFilter] = useState<'all' | '3' | '7' | '14'>('all')
  const [noteModal, setNoteModal] = useState<{ id: number; status: string } | null>(null)
  const [noteText, setNoteText] = useState('')
  const [blockerModal, setBlockerModal] = useState<{ id: number; title: string; reason?: string | null; note?: string | null; reviewOn?: string | null } | null>(null)
  const [blockerReason, setBlockerReason] = useState('')
  const [blockerNote, setBlockerNote] = useState('')
  const [blockerReviewOn, setBlockerReviewOn] = useState('')
  const [expandedComments, setExpandedComments] = useState<Set<number>>(new Set())
  const [selectedRequestIds, setSelectedRequestIds] = useState<Set<number>>(new Set())
  const [duplicateSelections, setDuplicateSelections] = useState<DuplicateSelectionState>({})
  const [slaStateFilter, setSlaStateFilter] = useState<'all' | 'breached' | 'due_soon' | 'on_track'>('all')
  const [slaTargetDays, setSlaTargetDays] = useState(7)
  const [slaWarningDays, setSlaWarningDays] = useState(2)
  const [slaRecommendedWarningOverride, setSlaRecommendedWarningOverride] = useState('')
  const [slaRecommendationFeedback, setSlaRecommendationFeedback] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)
  const [slaSelectedIds, setSlaSelectedIds] = useState<Set<number>>(new Set())
  const [slaEscalationNote, setSlaEscalationNote] = useState('')
  const [slaSimulationTargets, setSlaSimulationTargets] = useState('3,5,7,10,14')

  const toggleComments = (id: number) => {
    setExpandedComments((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const queryClient = useQueryClient()
  const { user: currentUser } = useAuth()

  const { data: stats } = useQuery({
    queryKey: ['adminStats'],
    queryFn: getAdminStats,
  })

  const { data: replyPack } = useQuery({
    queryKey: ['adminReplyPack'],
    queryFn: () => getAdminReplyPack(8),
    enabled: tab === 'requests',
  })

  const { data: requesterDigestPack } = useQuery({
    queryKey: ['requesterDigestPack'],
    queryFn: () => getRequesterDigestPack(6),
    enabled: tab === 'requests',
  })

  const { data: requestReviewLoop } = useQuery({
    queryKey: ['requestReviewLoop'],
    queryFn: () => getRequestReviewLoop(8),
    enabled: tab === 'requests',
  })

  const { data, isLoading } = useQuery({
    queryKey: ['adminRequests', sortBy, mediaTypeFilter],
    queryFn: () => getAllRequests(1, 500, undefined, sortBy, mediaTypeFilter === 'all' ? undefined : mediaTypeFilter),
    enabled: tab === 'requests',
  })

  const { data: duplicateGroups, isLoading: duplicatesLoading } = useQuery({
    queryKey: ['duplicateRequestGroups'],
    queryFn: getDuplicateRequestGroups,
    enabled: tab === 'duplicates',
  })

  const { data: slaPolicy } = useQuery({
    queryKey: ['slaPolicy'],
    queryFn: getSlaPolicy,
    enabled: tab === 'sla',
  })

  const { data: slaAnalytics, isLoading: slaAnalyticsLoading } = useQuery<AdminAnalytics>({
    queryKey: ['admin-analytics'],
    queryFn: getAnalytics,
    enabled: tab === 'sla',
  })

  const parsedSimulationTargets = Array.from(
    new Set(
      slaSimulationTargets
        .split(',')
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value) && value > 0 && value <= 90)
    )
  )

  const { data: slaSimulation, isLoading: slaSimulationLoading } = useQuery({
    queryKey: ['slaSimulation', parsedSimulationTargets.join(',')],
    queryFn: () => simulateSlaPolicy(parsedSimulationTargets),
    enabled: tab === 'sla' && parsedSimulationTargets.length > 0,
  })

  const { data: slaWorklist, isLoading: slaLoading } = useQuery({
    queryKey: ['slaWorklist', slaStateFilter],
    queryFn: () => getSlaWorklist(slaStateFilter),
    enabled: tab === 'sla',
  })

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ['adminUsers'],
    queryFn: getUsers,
    enabled: tab === 'users',
  })

  const { data: blStats } = useQuery({
    queryKey: ['backlogStats'],
    queryFn: getBacklogStats,
    enabled: tab === 'backlog',
  })

  const { data: backlogData, isLoading: backlogLoading } = useQuery({
    queryKey: ['adminBacklog'],
    queryFn: () => getAllBacklog(),
    enabled: tab === 'backlog',
  })

  const backlogMutation = useMutation({
    mutationFn: ({ id, ...updates }: { id: number; status?: string; priority?: string; admin_note?: string }) =>
      updateBacklogItem(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminBacklog'] })
      queryClient.invalidateQueries({ queryKey: ['backlogStats'] })
    },
  })

  const backlogDeleteMutation = useMutation({
    mutationFn: (id: number) => deleteBacklogItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminBacklog'] })
      queryClient.invalidateQueries({ queryKey: ['backlogStats'] })
    },
  })

  const allBacklog: any[] = backlogData?.items || []

  const [blNoteModal, setBlNoteModal] = useState<{ id: number; status: string } | null>(null)
  const [blNoteText, setBlNoteText] = useState('')

  const handleBacklogMove = (id: number, status: string) => {
    setBlNoteModal({ id, status })
    setBlNoteText('')
  }

  const confirmBacklogMove = () => {
    if (blNoteModal) {
      backlogMutation.mutate({ id: blNoteModal.id, status: blNoteModal.status, admin_note: blNoteText || undefined })
      setBlNoteModal(null)
      setBlNoteText('')
    }
  }

  const updateMutation = useMutation({
    mutationFn: ({ id, status, note }: { id: number; status: string; note?: string }) =>
      updateRequest(id, status, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const mergeDuplicatesMutation = useMutation({
    mutationFn: ({ targetRequestId, sourceRequestIds }: { targetRequestId: number; sourceRequestIds: number[] }) =>
      mergeDuplicateRequests(targetRequestId, sourceRequestIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['duplicateRequestGroups'] })
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const blockerMutation = useMutation({
    mutationFn: ({ id, reason, review_on, note }: { id: number; reason: string; review_on: string; note?: string }) =>
      setRequestBlocker(id, { reason, review_on, note }),
    onSuccess: () => {
      setBlockerModal(null)
      setBlockerReason('')
      setBlockerNote('')
      setBlockerReviewOn('')
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['requestReviewLoop'] })
    },
  })

  const clearBlockerMutation = useMutation({
    mutationFn: (id: number) => clearRequestBlocker(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['requestReviewLoop'] })
    },
  })

  const bulkUpdateMutation = useMutation({
    mutationFn: ({ requestIds, status }: { requestIds: number[]; status: string }) =>
      bulkUpdateRequests(requestIds, status, `Bulk update from admin table (${requestIds.length} requests)`),
    onSuccess: () => {
      setSelectedRequestIds(new Set())
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const saveSlaPolicyMutation = useMutation({
    mutationFn: ({ targetDays, warningDays }: { targetDays: number; warningDays: number }) =>
      updateSlaPolicy(targetDays, warningDays),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slaPolicy'] })
      queryClient.invalidateQueries({ queryKey: ['slaWorklist'] })
      queryClient.invalidateQueries({ queryKey: ['admin-analytics'] })
      queryClient.invalidateQueries({ queryKey: ['adminStats'] })
    },
  })

  const applyRecommendedSlaPolicyMutation = useMutation({
    mutationFn: ({ warningDaysOverride }: { warningDaysOverride?: number }) =>
      applyRecommendedSlaPolicy(warningDaysOverride),
    onSuccess: (policy) => {
      setSlaRecommendedWarningOverride('')
      setSlaRecommendationFeedback({
        type: 'success',
        message: `Applied recommended SLA: ${policy.target_days} day target, ${policy.warning_days} day warning window.`,
      })
      queryClient.invalidateQueries({ queryKey: ['slaPolicy'] })
      queryClient.invalidateQueries({ queryKey: ['slaWorklist'] })
      queryClient.invalidateQueries({ queryKey: ['admin-analytics'] })
    },
    onError: (error: any) => {
      setSlaRecommendationFeedback({
        type: 'error',
        message: error?.response?.data?.detail || 'Failed to apply recommended SLA policy',
      })
    },
  })

  const escalateSlaMutation = useMutation({
    mutationFn: ({ requestIds, note }: { requestIds: number[]; note?: string }) =>
      bulkEscalateSlaRequests(requestIds, note),
    onSuccess: () => {
      setSlaSelectedIds(new Set())
      setSlaEscalationNote('')
      queryClient.invalidateQueries({ queryKey: ['slaWorklist'] })
      queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
    },
  })

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      updateUserRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminUsers'] })
    },
  })

  const { data: tunnelData, isLoading: tunnelLoading } = useQuery({
    queryKey: ['tunnelStatus'],
    queryFn: getTunnelStatus,
    enabled: tab === 'tunnel',
    refetchInterval: tab === 'tunnel' ? 10000 : false,
  })

  const startTunnelMutation = useMutation({
    mutationFn: startTunnel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tunnelStatus'] }),
  })

  const stopTunnelMutation = useMutation({
    mutationFn: stopTunnel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tunnelStatus'] }),
  })

  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['healthCheck'],
    queryFn: getHealthCheck,
    enabled: tab === 'health',
    refetchInterval: tab === 'health' ? 30000 : false,
  })

  const scanMutation = useMutation({
    mutationFn: triggerJellyfinScan,
  })

  const allRequests: any[] = data?.items || []
  const copyReplyNote = async (item: AdminReplyPackItem) => {
    const detail = item.next_step_by
      ? `${item.suggested_note}\n\nNext step: ${item.next_step_label || 'Follow up'} by ${new Date(item.next_step_by).toLocaleDateString()}.`
      : item.suggested_note
    await navigator.clipboard.writeText(detail)
  }
  const copyRequesterDigestNote = async (item: RequesterDigestPackItem) => {
    await navigator.clipboard.writeText(item.suggested_note)
  }
  const openBlockerModal = (req: any) => {
    setBlockerModal({
      id: req.id,
      title: req.title,
      reason: req.blocker_reason,
      note: req.blocker_note,
      reviewOn: req.blocker_review_on,
    })
    setBlockerReason(req.blocker_reason || '')
    setBlockerNote(req.blocker_note || '')
    setBlockerReviewOn(req.blocker_review_on ? String(req.blocker_review_on).slice(0, 10) : '')
  }
  const saveBlocker = () => {
    if (!blockerModal || !blockerReason.trim() || !blockerReviewOn) return
    blockerMutation.mutate({
      id: blockerModal.id,
      reason: blockerReason.trim(),
      review_on: blockerReviewOn,
      note: blockerNote.trim() || undefined,
    })
  }
  const copyReviewLoopNote = async (item: RequestReviewLoopItem) => {
    const lines = [
      `${item.title} is blocked: ${item.reason}.`,
      `Next review on ${new Date(item.review_on).toLocaleDateString()}.`,
    ]
    if (item.note) lines.push(item.note)
    await navigator.clipboard.writeText(lines.join(' '))
  }
  const minAge = ageFilter === 'all' ? 0 : Number(ageFilter)
  const displayedRequests =
    minAge === 0
      ? allRequests
      : allRequests.filter((req) =>
          ['pending', 'approved'].includes(req.status) ? (req.days_open || 0) >= minAge : true
        )

  useEffect(() => {
    if (!duplicateGroups) return

    setDuplicateSelections((prev) => {
      const next: DuplicateSelectionState = {}

      duplicateGroups.forEach((group) => {
        const requestIds = group.requests.map((request) => request.id)
        if (requestIds.length === 0) return

        const existing = prev[group.group_id]
        const targetId =
          existing && requestIds.includes(existing.targetId)
            ? existing.targetId
            : group.requests[0].id
        const existingSourceIds = existing?.sourceIds.filter(
          (sourceId) => requestIds.includes(sourceId) && sourceId !== targetId
        ) || []

        next[group.group_id] = {
          targetId,
          sourceIds: existingSourceIds.length > 0 ? existingSourceIds : requestIds.filter((id) => id !== targetId),
        }
      })

      return next
    })
  }, [duplicateGroups])

  useEffect(() => {
    if (!slaPolicy) return
    setSlaTargetDays(slaPolicy.target_days)
    setSlaWarningDays(slaPolicy.warning_days)
  }, [slaPolicy])

  const toggleSlaSelection = (requestId: number) => {
    setSlaSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(requestId)) next.delete(requestId)
      else next.add(requestId)
      return next
    })
  }

  const toggleSelectAllSla = () => {
    const ids = (slaWorklist?.items || []).map((item: any) => item.id)
    const allSelected = ids.length > 0 && ids.every((id: number) => slaSelectedIds.has(id))
    setSlaSelectedIds((prev) => {
      const next = new Set(prev)
      if (allSelected) ids.forEach((id: number) => next.delete(id))
      else ids.forEach((id: number) => next.add(id))
      return next
    })
  }

  const saveSlaPolicy = () => {
    if (slaWarningDays >= slaTargetDays) return
    setSlaRecommendationFeedback(null)
    saveSlaPolicyMutation.mutate({ targetDays: slaTargetDays, warningDays: slaWarningDays })
  }

  const trimmedSlaRecommendedWarningOverride = slaRecommendedWarningOverride.trim()
  const slaAdvisor = slaAnalytics?.sla_policy_advisor
  const slaAdvisorTone =
    slaAdvisor?.recommended_action === 'tighten'
      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
      : slaAdvisor?.recommended_action === 'relax'
      ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
      : 'border-slate-700 bg-slate-800/60 text-slate-200'
  const hasSlaRecommendedWarningOverride = trimmedSlaRecommendedWarningOverride !== ''
  const parsedSlaRecommendedWarningOverride =
    hasSlaRecommendedWarningOverride ? Number(trimmedSlaRecommendedWarningOverride) : null
  const slaRecommendedWarningOverrideIsValid =
    !hasSlaRecommendedWarningOverride ||
    (
      parsedSlaRecommendedWarningOverride !== null &&
      Number.isInteger(parsedSlaRecommendedWarningOverride) &&
      parsedSlaRecommendedWarningOverride >= 0
    )
  const recommendedSlaDays = slaAnalytics?.recommended_sla_days ?? null
  const recommendedSlaWithinRate = slaAnalytics?.recommended_sla_within_rate ?? null
  const recommendedSlaSampleSize = slaAnalytics?.recommended_sla_sample_size ?? 0
  const defaultRecommendedWarningDays =
    recommendedSlaDays === null ? null : Math.min(Math.max(recommendedSlaDays - 2, 0), Math.max(recommendedSlaDays - 1, 0))

  const applyRecommendedPolicy = () => {
    if (recommendedSlaDays === null || !slaRecommendedWarningOverrideIsValid) return
    setSlaRecommendationFeedback(null)
    applyRecommendedSlaPolicyMutation.mutate({
      warningDaysOverride: parsedSlaRecommendedWarningOverride ?? undefined,
    })
  }

  const applySimulatedPolicy = (scenario: SlaSimulationScenario) => {
    setSlaTargetDays(scenario.target_days)
    setSlaWarningDays(scenario.warning_days)
    setSlaRecommendationFeedback(null)
    saveSlaPolicyMutation.mutate({
      targetDays: scenario.target_days,
      warningDays: scenario.warning_days,
    })
  }

  const escalateSelectedSla = () => {
    if (slaSelectedIds.size === 0) return
    escalateSlaMutation.mutate({ requestIds: Array.from(slaSelectedIds), note: slaEscalationNote || undefined })
  }

  const getAgeBadgeClass = (daysOpen: number) => {
    if (daysOpen >= 14) return 'bg-red-600/20 text-red-300 border border-red-500/30'
    if (daysOpen >= 7) return 'bg-amber-600/20 text-amber-300 border border-amber-500/30'
    if (daysOpen >= 3) return 'bg-yellow-600/20 text-yellow-300 border border-yellow-500/30'
    return 'bg-slate-700 text-slate-300 border border-slate-600'
  }

  const handleMove = (id: number, status: string) => {
    setNoteModal({ id, status })
    setNoteText('')
  }

  const confirmMove = () => {
    if (noteModal) {
      updateMutation.mutate({ id: noteModal.id, status: noteModal.status, note: noteText || undefined })
      setNoteModal(null)
      setNoteText('')
    }
  }

  const quickMove = (id: number, status: string) => {
    updateMutation.mutate({ id, status })
  }

  const toggleRequestSelection = (requestId: number) => {
    setSelectedRequestIds((prev) => {
      const next = new Set(prev)
      if (next.has(requestId)) next.delete(requestId)
      else next.add(requestId)
      return next
    })
  }

  const toggleSelectAllDisplayed = () => {
    const visibleIds = displayedRequests.map((req: any) => req.id)
    const allSelected = visibleIds.length > 0 && visibleIds.every((id: number) => selectedRequestIds.has(id))
    setSelectedRequestIds((prev) => {
      const next = new Set(prev)
      if (allSelected) visibleIds.forEach((id: number) => next.delete(id))
      else visibleIds.forEach((id: number) => next.add(id))
      return next
    })
  }

  const bulkMove = (status: string) => {
    if (selectedRequestIds.size === 0) return
    bulkUpdateMutation.mutate({ requestIds: Array.from(selectedRequestIds), status })
  }

  const getDuplicateSelection = (group: DuplicateGroup) =>
    duplicateSelections[group.group_id] || {
      targetId: group.requests[0]?.id || 0,
      sourceIds: group.requests.slice(1).map((request) => request.id),
    }

  const updateDuplicateTarget = (group: DuplicateGroup, targetId: number) => {
    const requestIds = group.requests.map((request) => request.id)
    setDuplicateSelections((prev) => ({
      ...prev,
      [group.group_id]: {
        targetId,
        sourceIds: requestIds.filter((requestId) => requestId !== targetId),
      },
    }))
  }

  const toggleDuplicateSource = (group: DuplicateGroup, sourceId: number) => {
    const fallback = getDuplicateSelection(group)
    if (fallback.targetId === sourceId) return

    setDuplicateSelections((prev) => {
      const current = prev[group.group_id] || fallback
      const alreadySelected = current.sourceIds.includes(sourceId)
      return {
        ...prev,
        [group.group_id]: {
          targetId: current.targetId,
          sourceIds: alreadySelected
            ? current.sourceIds.filter((requestId) => requestId !== sourceId)
            : [...current.sourceIds, sourceId].sort((left, right) => left - right),
        },
      }
    })
  }

  const mergeDuplicateGroup = (group: DuplicateGroup) => {
    const selection = getDuplicateSelection(group)
    if (!selection.targetId || selection.sourceIds.length === 0) return
    mergeDuplicatesMutation.mutate({
      targetRequestId: selection.targetId,
      sourceRequestIds: selection.sourceIds,
    })
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <h2 className="text-2xl font-bold text-white">Admin Panel</h2>
        <div className="flex gap-2">
          {tab === 'requests' && (
            <>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'priority' | 'newest' | 'oldest' | 'supporters')}
                className="px-3 py-1.5 rounded text-sm bg-slate-800 text-slate-300 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="priority">Sort: Priority</option>
                <option value="supporters">Sort: Most Supporters</option>
                <option value="newest">Sort: Newest</option>
                <option value="oldest">Sort: Oldest</option>
              </select>
              <select
                value={mediaTypeFilter}
                onChange={(e) => setMediaTypeFilter(e.target.value as 'all' | 'movie' | 'tv' | 'book')}
                className="px-3 py-1.5 rounded text-sm bg-slate-800 text-slate-300 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">Type: All</option>
                <option value="movie">Type: Movies</option>
                <option value="tv">Type: TV</option>
                <option value="book">Type: Books</option>
              </select>
              <select
                value={ageFilter}
                onChange={(e) => setAgeFilter(e.target.value as 'all' | '3' | '7' | '14')}
                className="px-3 py-1.5 rounded text-sm bg-slate-800 text-slate-300 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">Age: All</option>
                <option value="3">Age: 3+ days</option>
                <option value="7">Age: 7+ days</option>
                <option value="14">Age: 14+ days</option>
              </select>
              <button
                onClick={() => setView('board')}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  view === 'board' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                Board
              </button>
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  view === 'table' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                Table
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 mb-6 border-b border-slate-700 overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
        <button
          onClick={() => setTab('requests')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'requests'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Requests
        </button>
        <button
          onClick={() => setTab('duplicates')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'duplicates'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Duplicates
        </button>
        <button
          onClick={() => setTab('sla')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'sla'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          SLA
        </button>
        <button
          onClick={() => setTab('backlog')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'backlog'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Backlog
        </button>
        <button
          onClick={() => setTab('users')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'users'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Users
        </button>
        <button
          onClick={() => setTab('tunnel')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'tunnel'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Tunnel
        </button>
        <button
          onClick={() => setTab('health')}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
            tab === 'health'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          Health
        </button>
      </div>

      {/* ========== REQUESTS TAB ========== */}
      {tab === 'requests' && (
        <>
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
              <StatsCard label="Total Requests" value={stats.total} />
              <StatsCard label="Pending" value={stats.pending} />
              <StatsCard label="Approved" value={stats.approved} />
              <StatsCard label="Fulfilled" value={stats.fulfilled} />
              <StatsCard label="Unique Users" value={stats.unique_users} />
              <StatsCard label="Open 3+ days" value={stats.open_over_3_days || 0} />
              <StatsCard label="Open 7+ days" value={stats.open_over_7_days || 0} />
              <StatsCard label="Open 14+ days" value={stats.open_over_14_days || 0} />
              <StatsCard label="Oldest Open (days)" value={stats.oldest_open_days || 0} />
            </div>
          )}

          {isLoading && <p className="text-slate-400">Loading...</p>}

          {!isLoading && (stats?.open_over_7_days || 0) > 0 && (
            <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              ⚠ Queue aging alert: {stats?.open_over_7_days || 0} open request{(stats?.open_over_7_days || 0) === 1 ? '' : 's'} over 7 days old.
            </div>
          )}

          {!isLoading && allRequests.length > 0 && (
            <FulfillmentLinkRecoveryPanel
              items={allRequests}
              onLinked={() => {
                queryClient.invalidateQueries({ queryKey: ['adminRequests'] })
                queryClient.invalidateQueries({ queryKey: ['myRequests'] })
              }}
            />
          )}

          {!isLoading && requestReviewLoop && requestReviewLoop.summary.total > 0 && (
            <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-white font-semibold">Blocked Review Loop</h3>
                  <p className="text-sm text-slate-300">Keep blocked titles visible so they do not vanish into polite limbo.</p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full bg-red-500/15 px-2 py-1 text-red-300">{requestReviewLoop.summary.overdue} overdue</span>
                  <span className="rounded-full bg-amber-500/15 px-2 py-1 text-amber-300">{requestReviewLoop.summary.today} today</span>
                  <span className="rounded-full bg-blue-500/15 px-2 py-1 text-blue-300">{requestReviewLoop.summary.upcoming} upcoming</span>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-2">
                {requestReviewLoop.items.map((item) => (
                  <div key={item.request_id} className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-white">{item.title}</p>
                          <RequestBadge status={item.status} />
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${item.lane === 'overdue' ? 'bg-red-500/15 text-red-300' : item.lane === 'today' ? 'bg-amber-500/15 text-amber-300' : 'bg-blue-500/15 text-blue-300'}`}>
                            {item.lane}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">{item.username} · {item.supporter_count} supporters · {item.days_open}d open</p>
                      </div>
                      <button onClick={() => copyReviewLoopNote(item)} className="rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800">Copy update</button>
                    </div>
                    <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
                      <p>{item.reason}</p>
                      {item.note && <p className="mt-1 text-xs text-amber-200/80">{item.note}</p>}
                      <p className="mt-1 text-xs text-amber-200/80">Review on {new Date(item.review_on).toLocaleDateString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!isLoading && replyPack && replyPack.summary.total > 0 && (
            <div className="mb-6 rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4 space-y-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-white font-semibold">Reply Pack</h3>
                  <p className="text-sm text-slate-300">Requests most likely to trigger DM churn unless the queue speaks first.</p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full bg-red-500/15 px-2 py-1 text-red-300">{replyPack.summary.critical} critical</span>
                  <span className="rounded-full bg-amber-500/15 px-2 py-1 text-amber-300">{replyPack.summary.high} high</span>
                  <span className="rounded-full bg-blue-500/15 px-2 py-1 text-blue-300">{replyPack.summary.medium} medium</span>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-2">
                {replyPack.items.map((item) => (
                  <div key={item.id} className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-white">{item.title}</p>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${item.urgency === 'critical' ? 'bg-red-500/15 text-red-300' : item.urgency === 'high' ? 'bg-amber-500/15 text-amber-300' : 'bg-blue-500/15 text-blue-300'}`}>
                            {item.urgency}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">{item.username} · {item.media_type.toUpperCase()} · {item.days_open}d open · {item.supporter_count} supporter{item.supporter_count === 1 ? '' : 's'}</p>
                      </div>
                      <button
                        onClick={() => copyReplyNote(item)}
                        className="rounded bg-cyan-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-cyan-500"
                      >
                        Copy note
                      </button>
                    </div>
                    <p className="text-sm text-slate-200">{item.reason}</p>
                    {item.queue_reason && <p className="text-xs text-slate-400">{item.queue_reason}</p>}
                    <div className="rounded border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs text-slate-200">
                      {item.suggested_note}
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                      {item.queue_position && item.queue_size && <span>Queue #{item.queue_position} of {item.queue_size}</span>}
                      {item.next_step_label && <span>{item.next_step_label}{item.next_step_by ? ` by ${new Date(item.next_step_by).toLocaleDateString()}` : ''}</span>}
                      {item.eta_label && <span>{item.eta_label}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!isLoading && requesterDigestPack && requesterDigestPack.summary.total > 0 && (
            <div className="mb-6 rounded-xl border border-violet-500/30 bg-violet-500/5 p-4 space-y-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-white font-semibold">Requester Digest Pack</h3>
                  <p className="text-sm text-slate-300">Batch the people with multiple live asks into one clean status note instead of playing DM whack-a-mole.</p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full bg-red-500/15 px-2 py-1 text-red-300">{requesterDigestPack.summary.critical} critical</span>
                  <span className="rounded-full bg-amber-500/15 px-2 py-1 text-amber-300">{requesterDigestPack.summary.high} high</span>
                  <span className="rounded-full bg-blue-500/15 px-2 py-1 text-blue-300">{requesterDigestPack.summary.medium} medium</span>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-2">
                {requesterDigestPack.items.map((item) => (
                  <div key={item.user_id} className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-white">{item.username}</p>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${item.urgency === 'critical' ? 'bg-red-500/15 text-red-300' : item.urgency === 'high' ? 'bg-amber-500/15 text-amber-300' : 'bg-blue-500/15 text-blue-300'}`}>
                            {item.urgency}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">{item.open_request_count} open · {item.approved_count} approved · {item.pending_count} pending · {item.total_supporters} total supporters</p>
                      </div>
                      <button
                        onClick={() => copyRequesterDigestNote(item)}
                        className="rounded bg-violet-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-violet-500"
                      >
                        Copy digest
                      </button>
                    </div>

                    <p className="text-sm text-slate-200">{item.reason}</p>

                    <div className="flex flex-wrap gap-2 text-xs text-slate-400">
                      {item.breached_count > 0 && <span>{item.breached_count} breached</span>}
                      {item.at_risk_count > 0 && <span>{item.at_risk_count} at risk</span>}
                      <span>{item.request_titles.slice(0, 3).join(', ')}{item.request_titles.length > 3 ? ` +${item.request_titles.length - 3} more` : ''}</span>
                    </div>

                    <div className="space-y-2 rounded border border-slate-700 bg-slate-950/50 px-3 py-3">
                      {item.requests.slice(0, 4).map((request) => (
                        <div key={request.id} className="text-xs text-slate-300">
                          <span className="font-medium text-white">{request.title}</span>
                          <span className="text-slate-500"> · {request.status}</span>
                          <div className="text-slate-400">
                            {request.queue_position && request.queue_size
                              ? `Queue #${request.queue_position} of ${request.queue_size}`
                              : request.next_step_label || request.eta_label || request.promise_status || 'Still active'}
                            {request.eta_label && !(request.queue_position && request.queue_size) ? '' : ''}
                            {request.eta_label ? ` · ${request.eta_label}` : ''}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="rounded border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs whitespace-pre-line text-slate-200">
                      {item.suggested_note}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Board View */}
          {!isLoading && view === 'board' && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {COLUMNS.map((col) => {
                const items = displayedRequests.filter((r) => r.status === col.key)
                const transitions = TRANSITIONS[col.key] || []
                return (
                  <div key={col.key} className={`rounded-lg border-t-2 ${col.color} ${col.bg}`}>
                    <div className="p-4 border-b border-slate-700/50">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold text-white">{col.label}</h3>
                        <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                          {items.length}
                        </span>
                      </div>
                    </div>
                    <div className="p-2 space-y-2 max-h-[calc(100vh-340px)] overflow-y-auto">
                      {items.length === 0 && (
                        <p className="text-slate-500 text-xs text-center py-6">No requests</p>
                      )}
                      {items.map((req: any) => (
                        <div key={req.id} className="bg-slate-800 rounded-lg p-3 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-white truncate">{req.title}</p>
                              <p className="text-xs text-slate-400">
                                {req.username} &middot; {req.media_type.toUpperCase()} &middot;{' '}
                                {new Date(req.created_at).toLocaleDateString()}
                              </p>
                              <p className="text-xs text-slate-500 mt-0.5">{req.supporter_count || 1} supporter{(req.supporter_count || 1) === 1 ? '' : 's'} · score {req.priority_score || 0}</p>
                              {['pending', 'approved'].includes(req.status) && (
                                <span className={`mt-1 inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium ${getAgeBadgeClass(req.days_open || 0)}`}>
                                  {req.days_open || 0}d open
                                </span>
                              )}
                            </div>
                          </div>
                          {req.admin_note && (
                            <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">
                              {req.admin_note}
                            </p>
                          )}
                          {req.blocker_reason && (
                            <div className={`rounded-lg border px-3 py-2 text-xs ${req.blocker_is_overdue ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                              <p className="font-medium">Blocked: {req.blocker_reason}</p>
                              {req.blocker_note && <p className="mt-1 opacity-80">{req.blocker_note}</p>}
                              {req.blocker_review_on && <p className="mt-1 opacity-80">Review on {new Date(req.blocker_review_on).toLocaleDateString()}</p>}
                            </div>
                          )}
                          {req.watch_url && (
                            <a
                              href={req.watch_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-1 bg-green-600/20 hover:bg-green-600/40 text-green-400 text-xs font-medium rounded transition-colors"
                            >
                              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" /></svg>
                              Watch in Jellyfin
                            </a>
                          )}
                          {req.status === 'fulfilled' && !req.watch_url && (
                            <p className="text-xs text-amber-500/70 italic">⚠ No Jellyfin link</p>
                          )}
                          {transitions.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {transitions.map((t) => (
                                <button
                                  key={t.status}
                                  onClick={() => handleMove(req.id, t.status)}
                                  disabled={updateMutation.isPending}
                                  className={`px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 ${t.style}`}
                                >
                                  {t.label}
                                </button>
                              ))}
                            </div>
                          )}
                          <button
                            onClick={() => toggleComments(req.id)}
                            className="text-xs text-slate-500 hover:text-blue-400 transition-colors pt-0.5"
                          >
                            {expandedComments.has(req.id) ? '▲ Hide comments' : '💬 Comments'}
                          </button>
                          {['pending', 'approved'].includes(req.status) && (
                            <button
                              onClick={() => openBlockerModal(req)}
                              className="text-xs text-amber-300 hover:text-amber-200 transition-colors pt-0.5"
                            >
                              {req.blocker_reason ? '⏱ Edit blocker' : '⏱ Set blocker'}
                            </button>
                          )}
                          {req.blocker_reason && (
                            <button
                              onClick={() => clearBlockerMutation.mutate(req.id)}
                              className="text-xs text-slate-400 hover:text-white transition-colors pt-0.5"
                            >
                              Clear blocker
                            </button>
                          )}
                          {expandedComments.has(req.id) && (
                            <RequestComments requestId={req.id} />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Table View */}
          {!isLoading && view === 'table' && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2">
                <span className="text-xs text-slate-400">{selectedRequestIds.size} selected</span>
                <button onClick={toggleSelectAllDisplayed} className="text-xs text-blue-400 hover:text-blue-300">Toggle all visible</button>
                <div className="h-4 w-px bg-slate-700" />
                <button onClick={() => bulkMove('approved')} disabled={selectedRequestIds.size === 0 || bulkUpdateMutation.isPending} className="px-2 py-1 rounded text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-40">Approve</button>
                <button onClick={() => bulkMove('fulfilled')} disabled={selectedRequestIds.size === 0 || bulkUpdateMutation.isPending} className="px-2 py-1 rounded text-xs font-medium bg-green-600 hover:bg-green-700 text-white disabled:opacity-40">Fulfill</button>
                <button onClick={() => bulkMove('denied')} disabled={selectedRequestIds.size === 0 || bulkUpdateMutation.isPending} className="px-2 py-1 rounded text-xs font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-40">Deny</button>
                <button onClick={() => bulkMove('pending')} disabled={selectedRequestIds.size === 0 || bulkUpdateMutation.isPending} className="px-2 py-1 rounded text-xs font-medium bg-yellow-600 hover:bg-yellow-700 text-white disabled:opacity-40">Move to Pending</button>
              </div>
              <div className="bg-slate-800 rounded-lg overflow-hidden overflow-x-auto">
                <table className="w-full min-w-[700px]">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">
                        <input type="checkbox" checked={displayedRequests.length > 0 && displayedRequests.every((req: any) => selectedRequestIds.has(req.id))} onChange={toggleSelectAllDisplayed} className="rounded border-slate-500 bg-slate-900 text-blue-500 focus:ring-blue-500" />
                      </th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Title</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Type</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">User</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Supporters</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Age</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Status</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Date</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Note</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Watch</th>
                      <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Move to</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedRequests.map((req: any) => {
                      const transitions = TRANSITIONS[req.status] || []
                      return (
                        <tr key={req.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                          <td className="px-4 py-3"><input type="checkbox" checked={selectedRequestIds.has(req.id)} onChange={() => toggleRequestSelection(req.id)} className="rounded border-slate-500 bg-slate-900 text-blue-500 focus:ring-blue-500" /></td>
                          <td className="px-4 py-3 text-white text-sm">{req.title}</td>
                          <td className="px-4 py-3 text-slate-400 text-sm uppercase">{req.media_type}</td>
                          <td className="px-4 py-3 text-slate-300 text-sm">{req.username}</td>
                          <td className="px-4 py-3 text-slate-400 text-sm">{req.supporter_count || 1}<div className="text-[11px] text-slate-500">score {req.priority_score || 0}</div></td>
                          <td className="px-4 py-3 text-sm">
                            {['pending', 'approved'].includes(req.status) ? (
                              <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium ${getAgeBadgeClass(req.days_open || 0)}`}>
                                {req.days_open || 0}d open
                              </span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3"><RequestBadge status={req.status} /></td>
                          <td className="px-4 py-3 text-slate-400 text-sm">{new Date(req.created_at).toLocaleDateString()}</td>
                          <td className="px-4 py-3 text-slate-400 text-sm max-w-56">
                            <div className="space-y-1">
                              <div className="truncate">{req.admin_note || '-'}</div>
                              {req.blocker_reason && (
                                <div className={`rounded border px-2 py-1 text-xs ${req.blocker_is_overdue ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                                  <div>{req.blocker_reason}</div>
                                  {req.blocker_review_on && <div className="opacity-80 mt-0.5">Review {new Date(req.blocker_review_on).toLocaleDateString()}</div>}
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {req.watch_url ? (
                              <a href={req.watch_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 px-2 py-1 bg-green-600/20 hover:bg-green-600/40 text-green-400 text-xs font-medium rounded transition-colors">
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" /></svg>
                                Watch
                              </a>
                            ) : req.status === 'fulfilled' ? (
                              <span className="text-xs text-amber-500/60">No link</span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-1.5">
                              {transitions.map((t) => (
                                <button key={t.status} onClick={() => quickMove(req.id, t.status)} disabled={updateMutation.isPending} className={`px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 ${t.style}`}>
                                  {t.label}
                                </button>
                              ))}
                              {['pending', 'approved'].includes(req.status) && (
                                <button onClick={() => openBlockerModal(req)} className="px-2 py-1 rounded text-xs font-medium bg-amber-600 hover:bg-amber-700 text-white">
                                  {req.blocker_reason ? 'Edit blocker' : 'Set blocker'}
                                </button>
                              )}
                              {req.blocker_reason && (
                                <button onClick={() => clearBlockerMutation.mutate(req.id)} className="px-2 py-1 rounded text-xs font-medium bg-slate-700 hover:bg-slate-600 text-white">
                                  Clear
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {/* ========== DUPLICATES TAB ========== */}
      {tab === 'duplicates' && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">
            Pick a canonical request for each active duplicate group. Selected source requests will be denied, their supporters
            will move to the target, and impacted users will be notified.
          </div>

          {duplicatesLoading && <p className="text-slate-400">Scanning active requests for likely duplicates...</p>}

          {!duplicatesLoading && duplicateGroups && duplicateGroups.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/40 px-6 py-12 text-center">
              <p className="text-white font-medium">No active duplicate groups found.</p>
              <p className="text-sm text-slate-500 mt-2">Pending and approved requests are currently consolidated.</p>
            </div>
          )}

          {!duplicatesLoading && duplicateGroups && duplicateGroups.length > 0 && (
            <div className="space-y-4">
              {duplicateGroups.map((group) => {
                const selection = getDuplicateSelection(group)
                const isMergingGroup =
                  mergeDuplicatesMutation.isPending &&
                  mergeDuplicatesMutation.variables?.targetRequestId === selection.targetId

                return (
                  <div key={group.group_id} className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900/70">
                    <div className="flex flex-col gap-3 border-b border-slate-700/60 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-blue-600/20 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-blue-300">
                            {group.media_type}
                          </span>
                          {group.matched_by_title && (
                            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                              Same title
                            </span>
                          )}
                          {group.matched_by_tmdb && (
                            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                              Same TMDB
                            </span>
                          )}
                        </div>
                        <h3 className="mt-2 text-lg font-semibold text-white">
                          {group.requests[0]?.title || group.normalized_title}
                        </h3>
                        <p className="text-sm text-slate-400">
                          {group.requests.length} active requests · {group.total_supporters} combined supporters
                        </p>
                        {group.shared_tmdb_ids.length > 0 && (
                          <p className="mt-1 text-xs text-slate-500">
                            Shared TMDB IDs: {group.shared_tmdb_ids.join(', ')}
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col gap-2 lg:items-end">
                        <p className="max-w-sm text-xs text-slate-400">
                          The target keeps its current status. All selected source requests are merged into it and then denied.
                        </p>
                        <button
                          onClick={() => mergeDuplicateGroup(group)}
                          disabled={!selection.targetId || selection.sourceIds.length === 0 || mergeDuplicatesMutation.isPending}
                          className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-40"
                        >
                          {isMergingGroup ? 'Merging...' : `Merge ${selection.sourceIds.length} into #${selection.targetId}`}
                        </button>
                      </div>
                    </div>

                    <div className="divide-y divide-slate-800">
                      {group.requests.map((request) => {
                        const isTarget = selection.targetId === request.id
                        const selectedSource = selection.sourceIds.includes(request.id)

                        return (
                          <div
                            key={request.id}
                            className={`grid gap-3 px-4 py-4 lg:grid-cols-[96px,96px,minmax(0,1fr),88px,120px] ${
                              isTarget ? 'bg-blue-500/5' : ''
                            }`}
                          >
                            <label className="flex items-center gap-2 text-sm text-slate-300">
                              <input
                                type="radio"
                                name={`duplicate-target-${group.group_id}`}
                                checked={isTarget}
                                onChange={() => updateDuplicateTarget(group, request.id)}
                                className="h-4 w-4 border-slate-500 bg-slate-900 text-blue-500 focus:ring-blue-500"
                              />
                              <span>Target</span>
                            </label>

                            <label className="flex items-center gap-2 text-sm text-slate-300">
                              <input
                                type="checkbox"
                                checked={selectedSource}
                                onChange={() => toggleDuplicateSource(group, request.id)}
                                disabled={isTarget}
                                className="h-4 w-4 rounded border-slate-500 bg-slate-900 text-blue-500 focus:ring-blue-500 disabled:opacity-40"
                              />
                              <span>Merge</span>
                            </label>

                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-medium text-white">{request.title}</p>
                                <span className="text-xs text-slate-500">#{request.id}</span>
                                <RequestBadge status={request.status} />
                              </div>
                              <p className="mt-1 text-xs text-slate-400">
                                {request.username} · {request.supporter_count} supporter
                                {request.supporter_count === 1 ? '' : 's'} · {new Date(request.created_at).toLocaleDateString()}
                              </p>
                              {request.admin_note && (
                                <p className="mt-2 line-clamp-2 text-xs italic text-slate-500">{request.admin_note}</p>
                              )}
                            </div>

                            <div className="text-xs text-slate-400">
                              <p className="font-medium text-slate-300">TMDB</p>
                              <p>{request.tmdb_id}</p>
                            </div>

                            <div className="text-xs text-slate-500 lg:text-right">
                              {isTarget ? (
                                <span className="font-medium text-blue-300">Canonical target</span>
                              ) : selectedSource ? (
                                <span className="font-medium text-emerald-300">Will merge</span>
                              ) : (
                                <span>Not selected</span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {mergeDuplicatesMutation.isError && (
            <p className="text-sm text-red-400">
              {(mergeDuplicatesMutation.error as any)?.response?.data?.detail || 'Failed to merge duplicate requests'}
            </p>
          )}
        </div>
      )}

      {/* ========== SLA TAB ========== */}
      {tab === 'sla' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard label="Open Requests" value={slaWorklist?.summary.total_open || 0} />
            <StatsCard label="Breached" value={slaWorklist?.summary.breached || 0} />
            <StatsCard label="Due Soon" value={slaWorklist?.summary.due_soon || 0} />
            <StatsCard label="On Track" value={slaWorklist?.summary.on_track || 0} />
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <h3 className="text-white font-semibold">SLA Policy</h3>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-sm text-slate-300">Target days
                <input type="number" min={1} max={90} value={slaTargetDays} onChange={(e) => setSlaTargetDays(Number(e.target.value))}
                  className="mt-1 w-28 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-white" />
              </label>
              <label className="text-sm text-slate-300">Warn when ≤ days to breach
                <input type="number" min={0} max={30} value={slaWarningDays} onChange={(e) => setSlaWarningDays(Number(e.target.value))}
                  className="mt-1 w-28 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-white" />
              </label>
              <button onClick={saveSlaPolicy} disabled={saveSlaPolicyMutation.isPending || slaWarningDays >= slaTargetDays}
                className="px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-sm text-white font-medium">
                {saveSlaPolicyMutation.isPending ? 'Saving...' : 'Save Policy'}
              </button>
            </div>
            {slaWarningDays >= slaTargetDays && <p className="text-xs text-red-400">Warning window must be less than target days.</p>}

            <div className="border-t border-slate-800 pt-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Recommended</p>
                  {slaAnalyticsLoading ? (
                    <p className="text-sm text-slate-400">Loading recommendation...</p>
                  ) : recommendedSlaDays !== null && recommendedSlaWithinRate !== null ? (
                    <div className="flex flex-wrap items-center gap-2 text-sm text-slate-300">
                      <span className="rounded-full bg-blue-500/15 px-2 py-1 font-medium text-blue-200">
                        {recommendedSlaDays} day{recommendedSlaDays === 1 ? '' : 's'}
                      </span>
                      <span>{recommendedSlaWithinRate}% expected hit rate</span>
                      <span className="text-slate-500">{recommendedSlaSampleSize} fulfilled sample{recommendedSlaSampleSize === 1 ? '' : 's'}</span>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400">Needs fulfilled request history before a recommendation is available.</p>
                  )}
                </div>

                <div className="flex flex-wrap items-end gap-3">
                  <label className="text-sm text-slate-300">Warning override
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={slaRecommendedWarningOverride}
                      onChange={(e) => {
                        setSlaRecommendedWarningOverride(e.target.value)
                        setSlaRecommendationFeedback(null)
                      }}
                      placeholder={defaultRecommendedWarningDays === null ? 'Auto' : String(defaultRecommendedWarningDays)}
                      className="mt-1 w-32 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-white placeholder:text-slate-500"
                    />
                  </label>
                  <button
                    onClick={applyRecommendedPolicy}
                    disabled={
                      applyRecommendedSlaPolicyMutation.isPending ||
                      recommendedSlaDays === null ||
                      !slaRecommendedWarningOverrideIsValid
                    }
                    className="px-3 py-2 rounded bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-sm text-white font-medium"
                  >
                    {applyRecommendedSlaPolicyMutation.isPending ? 'Applying...' : 'Apply Recommended'}
                  </button>
                </div>
              </div>

              {defaultRecommendedWarningDays !== null && (
                <p className="mt-2 text-xs text-slate-500">
                  Leave the warning override blank to use {defaultRecommendedWarningDays} day{defaultRecommendedWarningDays === 1 ? '' : 's'} before breach.
                </p>
              )}
              {!slaRecommendedWarningOverrideIsValid && (
                <p className="mt-2 text-xs text-red-400">Warning override must be a whole number 0 or greater.</p>
              )}
              {slaRecommendationFeedback && (
                <p className={`mt-2 text-sm ${slaRecommendationFeedback.type === 'success' ? 'text-emerald-300' : 'text-red-400'}`}>
                  {slaRecommendationFeedback.message}
                </p>
              )}
            </div>
          </div>

          <div className={`rounded-lg border p-4 space-y-3 ${slaAdvisorTone}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-white">Household SLA Advisor</h3>
                <p className="text-sm opacity-90 mt-1">{slaAdvisor?.summary || 'Loading advisor...'}</p>
              </div>
              {slaAdvisor && (
                <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-wide">
                  <span className="rounded-full bg-slate-950/30 px-2 py-1 text-white/90">{slaAdvisor.recommended_action}</span>
                  <span className="rounded-full bg-slate-950/30 px-2 py-1 text-white/90">{slaAdvisor.confidence} confidence</span>
                  <span className="rounded-full bg-slate-950/30 px-2 py-1 text-white/90">{slaAdvisor.sample_size} fulfilled</span>
                </div>
              )}
            </div>

            {slaAdvisor && (
              <>
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded border border-white/10 bg-slate-950/20 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-300">Current policy</p>
                    <p className="mt-1 text-lg font-semibold text-white">{slaPolicy?.target_days ?? slaAnalytics?.sla_days}d</p>
                  </div>
                  <div className="rounded border border-white/10 bg-slate-950/20 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-300">Suggested target</p>
                    <p className="mt-1 text-lg font-semibold text-white">{slaAdvisor.suggested_target_days ?? '—'}{slaAdvisor.suggested_target_days ? 'd' : ''}</p>
                  </div>
                  <div className="rounded border border-white/10 bg-slate-950/20 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-300">Review trigger</p>
                    <p className="mt-1 text-sm text-slate-100">{slaAdvisor.review_trigger}</p>
                  </div>
                </div>

                <ul className="space-y-2 text-sm text-slate-100/90">
                  {slaAdvisor.reasons.map((reason, index) => (
                    <li key={`${index}-${reason}`} className="flex gap-2">
                      <span className="mt-0.5 text-slate-300">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>

                {slaAdvisor.suggested_target_days !== null && slaAdvisor.suggested_target_days !== slaTargetDays && (
                  <div>
                    <button
                      onClick={() => applySimulatedPolicy({
                        target_days: slaAdvisor.suggested_target_days!,
                        warning_days: Math.min(Math.max(slaAdvisor.suggested_target_days! - 2, 0), Math.max(slaAdvisor.suggested_target_days! - 1, 0)),
                      } as SlaSimulationScenario)}
                      disabled={saveSlaPolicyMutation.isPending}
                      className="px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-sm text-white font-medium"
                    >
                      Apply advisor target
                    </button>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <h3 className="text-white font-semibold">SLA Target Simulator</h3>
            <p className="text-sm text-slate-400">Compare candidate SLA targets against historical fulfillment hit rate and current queue risk before applying policy.</p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-sm text-slate-300">Candidate targets (days)
                <input
                  type="text"
                  value={slaSimulationTargets}
                  onChange={(e) => setSlaSimulationTargets(e.target.value)}
                  placeholder="3,5,7,10,14"
                  className="mt-1 w-56 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-white"
                />
              </label>
              {parsedSimulationTargets.length === 0 && <p className="text-xs text-red-400">Enter one or more comma-separated whole numbers between 1 and 90.</p>}
            </div>

            {slaSimulationLoading ? (
              <p className="text-sm text-slate-400">Simulating targets...</p>
            ) : (
              <div className="space-y-2 overflow-x-auto">
                {slaSimulation?.recommended_target_days !== null && slaSimulation?.recommended_target_days !== undefined && (
                  <p className="text-xs text-slate-400">
                    Recommended target for current queue pressure: <span className="font-semibold text-emerald-300">{slaSimulation.recommended_target_days}d</span>
                    {slaSimulation.current_target_days
                      ? ` (current policy: ${slaSimulation.current_target_days}d)`
                      : ''}
                  </p>
                )}
                <table className="w-full min-w-[860px]">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400 text-sm">
                      <th className="text-left px-3 py-2">Target</th>
                      <th className="text-left px-3 py-2">Auto warn</th>
                      <th className="text-left px-3 py-2">Historical hit rate</th>
                      <th className="text-left px-3 py-2">Open breaching</th>
                      <th className="text-left px-3 py-2">Open due soon</th>
                      <th className="text-left px-3 py-2">Risk score</th>
                      <th className="text-left px-3 py-2">Δ vs current</th>
                      <th className="text-left px-3 py-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(slaSimulation?.scenarios || []).map((scenario) => {
                      const delta = scenario.delta_vs_current
                      const formatDelta = (value: number) => (value > 0 ? `+${value}` : `${value}`)

                      return (
                        <tr key={scenario.target_days} className="border-b border-slate-800">
                          <td className="px-3 py-2 text-white text-sm">
                            <div className="flex items-center gap-2">
                              <span>{scenario.target_days}d</span>
                              {scenario.is_recommended && (
                                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                                  Recommended
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-slate-300 text-sm">{scenario.warning_days}d</td>
                          <td className="px-3 py-2 text-slate-300 text-sm">
                            {scenario.historical_hit_rate === null
                              ? 'No history yet'
                              : `${scenario.historical_hit_rate}% (${scenario.historical_within_count}/${scenario.historical_sample_size})`}
                          </td>
                          <td className="px-3 py-2 text-sm text-red-300">{scenario.open_breaching}</td>
                          <td className="px-3 py-2 text-sm text-amber-300">{scenario.open_due_soon}</td>
                          <td className="px-3 py-2 text-sm text-slate-200">{scenario.operational_risk_score}</td>
                          <td className="px-3 py-2 text-xs text-slate-300">
                            {delta ? (
                              <div className="space-y-0.5">
                                <div>Breaches: <span className={delta.open_breaching <= 0 ? 'text-emerald-300' : 'text-red-300'}>{formatDelta(delta.open_breaching)}</span></div>
                                <div>Due soon: <span className={delta.open_due_soon <= 0 ? 'text-emerald-300' : 'text-amber-300'}>{formatDelta(delta.open_due_soon)}</span></div>
                                <div>Risk: <span className={delta.operational_risk_score <= 0 ? 'text-emerald-300' : 'text-red-300'}>{formatDelta(delta.operational_risk_score)}</span></div>
                              </div>
                            ) : (
                              <span className="text-slate-500">Baseline</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => applySimulatedPolicy(scenario)}
                              disabled={saveSlaPolicyMutation.isPending}
                              className="px-2 py-1 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-xs text-white font-medium"
                            >
                              Apply
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <h3 className="text-white font-semibold">SLA Momentum (last 8 weeks)</h3>
            <p className="text-sm text-slate-400">Track whether SLA hit rate is improving or slipping week-to-week before changing policy.</p>

            {slaAnalytics && slaAnalytics.weekly_sla_hit_rate.length > 0 ? (
              <>
                <div className={`rounded border px-3 py-2 text-sm ${
                  slaAnalytics.sla_trend_direction === 'improving'
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                    : slaAnalytics.sla_trend_direction === 'regressing'
                    ? 'border-red-500/40 bg-red-500/10 text-red-200'
                    : 'border-slate-700 bg-slate-800/60 text-slate-300'
                }`}>
                  Trend: <span className="font-semibold capitalize">{slaAnalytics.sla_trend_direction}</span>
                  {' '}({slaAnalytics.sla_trend_delta > 0 ? '+' : ''}{slaAnalytics.sla_trend_delta} pts from oldest to newest week)
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-slate-700 text-slate-400 text-sm">
                        <th className="text-left px-3 py-2">Week</th>
                        <th className="text-left px-3 py-2">Within SLA</th>
                        <th className="text-left px-3 py-2">Fulfilled</th>
                        <th className="text-left px-3 py-2">Hit Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {slaAnalytics.weekly_sla_hit_rate.map((row) => (
                        <tr key={row.week} className="border-b border-slate-800">
                          <td className="px-3 py-2 text-sm text-white">{row.week}</td>
                          <td className="px-3 py-2 text-sm text-slate-300">{row.within_sla}</td>
                          <td className="px-3 py-2 text-sm text-slate-300">{row.fulfilled}</td>
                          <td className="px-3 py-2 text-sm text-slate-200">{row.hit_rate}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400">No weekly SLA history yet, fulfill a few requests to unlock momentum tracking.</p>
            )}
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <h3 className="text-white font-semibold">Media-type SLA Insights</h3>
            <p className="text-sm text-slate-400">Use this to decide whether one global SLA is fair for movies, shows, and books, before changing household policy.</p>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px]">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400 text-sm">
                    <th className="text-left px-3 py-2">Type</th>
                    <th className="text-left px-3 py-2">Fulfilled sample</th>
                    <th className="text-left px-3 py-2">Median lead time</th>
                    <th className="text-left px-3 py-2">Suggested target</th>
                    <th className="text-left px-3 py-2">Hit rate at suggested</th>
                    <th className="text-left px-3 py-2">Open count</th>
                    <th className="text-left px-3 py-2">Breaching current policy</th>
                    <th className="text-left px-3 py-2">Breaching suggested</th>
                  </tr>
                </thead>
                <tbody>
                  {(slaAnalytics?.media_type_sla_insights || []).map((row) => (
                    <tr key={row.media_type} className="border-b border-slate-800">
                      <td className="px-3 py-2 text-sm text-white uppercase">{row.media_type}</td>
                      <td className="px-3 py-2 text-sm text-slate-300">{row.fulfilled_sample_size}</td>
                      <td className="px-3 py-2 text-sm text-slate-300">
                        {row.median_lead_time_days === null ? 'No history yet' : `${row.median_lead_time_days}d`}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-200">
                        {row.recommended_target_days === null ? '—' : `${row.recommended_target_days}d`}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-300">
                        {row.recommended_within_rate === null ? '—' : `${row.recommended_within_rate}%`}
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-300">{row.open_count}</td>
                      <td className="px-3 py-2 text-sm text-red-300">{row.open_breaching_global_policy}</td>
                      <td className="px-3 py-2 text-sm text-amber-300">
                        {row.open_breaching_recommended === null ? '—' : row.open_breaching_recommended}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <select value={slaStateFilter} onChange={(e) => setSlaStateFilter(e.target.value as any)} className="px-3 py-1.5 rounded text-sm bg-slate-800 text-slate-300 border border-slate-700">
                <option value="all">All states</option>
                <option value="breached">Breached</option>
                <option value="due_soon">Due soon</option>
                <option value="on_track">On track</option>
              </select>
              <button onClick={toggleSelectAllSla} className="text-xs text-blue-400 hover:text-blue-300">Toggle all</button>
              <span className="text-xs text-slate-500">{slaSelectedIds.size} selected</span>
            </div>

            <textarea value={slaEscalationNote} onChange={(e) => setSlaEscalationNote(e.target.value)} placeholder="Optional escalation note for selected requests"
              rows={2} className="w-full rounded bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white" />
            <button onClick={escalateSelectedSla} disabled={slaSelectedIds.size === 0 || escalateSlaMutation.isPending}
              className="px-3 py-2 rounded bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-sm text-white font-medium">
              {escalateSlaMutation.isPending ? 'Escalating...' : 'Escalate selected'}
            </button>

            {slaLoading ? <p className="text-slate-400 text-sm">Loading SLA worklist...</p> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px]">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400 text-sm">
                      <th className="text-left px-3 py-2"></th>
                      <th className="text-left px-3 py-2">Title</th>
                      <th className="text-left px-3 py-2">Status</th>
                      <th className="text-left px-3 py-2">Age</th>
                      <th className="text-left px-3 py-2">Supporters</th>
                      <th className="text-left px-3 py-2">Days to breach</th>
                      <th className="text-left px-3 py-2">SLA state</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(slaWorklist?.items || []).map((item: any) => (
                      <tr key={item.id} className="border-b border-slate-800">
                        <td className="px-3 py-2"><input type="checkbox" checked={slaSelectedIds.has(item.id)} onChange={() => toggleSlaSelection(item.id)} /></td>
                        <td className="px-3 py-2 text-white text-sm">{item.title}</td>
                        <td className="px-3 py-2 text-sm"><RequestBadge status={item.status} /></td>
                        <td className="px-3 py-2 text-slate-300 text-sm">{item.days_open}d</td>
                        <td className="px-3 py-2 text-slate-300 text-sm">{item.supporter_count}</td>
                        <td className="px-3 py-2 text-slate-300 text-sm">{item.days_until_breach}</td>
                        <td className="px-3 py-2 text-sm">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${item.sla_state === 'breached' ? 'bg-red-600/30 text-red-300' : item.sla_state === 'due_soon' ? 'bg-amber-600/30 text-amber-300' : 'bg-green-600/30 text-green-300'}`}>
                            {item.sla_state}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========== BACKLOG TAB ========== */}
      {tab === 'backlog' && (
        <>
          {blStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <StatsCard label="Total Items" value={blStats.total} />
              <StatsCard label="Bugs" value={blStats.bugs} />
              <StatsCard label="Features" value={blStats.features} />
              <StatsCard label="Open" value={blStats.reported + blStats.triaged + blStats.in_progress + (blStats.ready_for_test || 0)} />
            </div>
          )}

          {backlogLoading && <p className="text-slate-400">Loading...</p>}

          {!backlogLoading && (
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-4">
              {BACKLOG_COLUMNS.map((col) => {
                const items = allBacklog.filter((r) => r.status === col.key)
                const transitions = BACKLOG_TRANSITIONS[col.key] || []
                return (
                  <div key={col.key} className={`rounded-lg border-t-2 ${col.color} ${col.bg}`}>
                    <div className="p-4 border-b border-slate-700/50">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold text-white text-sm">{col.label}</h3>
                        <span className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
                          {items.length}
                        </span>
                      </div>
                    </div>
                    <div className="p-2 space-y-2 max-h-[calc(100vh-380px)] overflow-y-auto">
                      {items.length === 0 && (
                        <p className="text-slate-500 text-xs text-center py-6">Empty</p>
                      )}
                      {items.map((item: any) => (
                        <div key={item.id} className="bg-slate-800 rounded-lg p-3 space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                    item.type === 'bug'
                                      ? 'bg-red-600/30 text-red-300'
                                      : 'bg-purple-600/30 text-purple-300'
                                  }`}
                                >
                                  {item.type}
                                </span>
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PRIORITY_STYLES[item.priority] || ''}`}
                                >
                                  {item.priority}
                                </span>
                              </div>
                              <p className="text-sm font-medium text-white leading-tight">{item.title}</p>
                              <p className="text-xs text-slate-400 mt-0.5">
                                {item.username} &middot; {new Date(item.created_at).toLocaleDateString()}
                              </p>
                            </div>
                            <button
                              onClick={() => backlogDeleteMutation.mutate(item.id)}
                              className="text-slate-500 hover:text-red-400 text-xs flex-shrink-0"
                              title="Delete"
                            >
                              x
                            </button>
                          </div>
                          {item.description && (
                            <p className="text-xs text-slate-400 line-clamp-2">{item.description}</p>
                          )}
                          {item.admin_note && (
                            <p className="text-xs text-slate-400 italic border-l-2 border-slate-600 pl-2">
                              {item.admin_note}
                            </p>
                          )}
                          {/* Priority selector */}
                          <div className="flex gap-1">
                            {['low', 'medium', 'high', 'critical'].map((p) => (
                              <button
                                key={p}
                                onClick={() => backlogMutation.mutate({ id: item.id, priority: p })}
                                className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                                  item.priority === p
                                    ? PRIORITY_STYLES[p]
                                    : 'bg-slate-700/50 text-slate-500 hover:text-slate-300'
                                }`}
                              >
                                {p}
                              </button>
                            ))}
                          </div>
                          {/* Status transitions */}
                          {transitions.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {transitions.map((t) => (
                                <button
                                  key={t.status}
                                  onClick={() => handleBacklogMove(item.id, t.status)}
                                  disabled={backlogMutation.isPending}
                                  className={`px-2 py-1 rounded text-xs font-medium transition-colors disabled:opacity-50 ${t.style}`}
                                >
                                  {t.label}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ========== USERS TAB ========== */}
      {tab === 'users' && (
        <div>
          <p className="text-slate-400 text-sm mb-6">
            Manage user roles. Admins can manage requests and other users. Users who have logged in at least once appear here.
          </p>

          {usersLoading && <p className="text-slate-400">Loading...</p>}

          {!usersLoading && users && users.length === 0 && (
            <p className="text-slate-500 text-center py-12">No users have logged in yet.</p>
          )}

          {/* Mobile card view */}
          {!usersLoading && users && users.length > 0 && (
            <div className="md:hidden space-y-3">
              {users.map((u: any) => {
                const isSelf = u.user_id === currentUser?.id
                return (
                  <div key={u.user_id} className="bg-slate-800 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">
                          {u.username}
                          {isSelf && <span className="ml-2 text-xs text-slate-500">(you)</span>}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          Joined {new Date(u.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded font-medium ${
                          u.role === 'admin'
                            ? 'bg-purple-600/30 text-purple-300'
                            : 'bg-slate-600/30 text-slate-300'
                        }`}
                      >
                        {u.role}
                      </span>
                    </div>
                    {!isSelf && (
                      <button
                        onClick={() => roleMutation.mutate({ userId: u.user_id, role: u.role === 'user' ? 'admin' : 'user' })}
                        disabled={roleMutation.isPending}
                        className={`w-full py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 ${
                          u.role === 'user'
                            ? 'bg-purple-600 hover:bg-purple-700 text-white'
                            : 'bg-slate-600 hover:bg-slate-500 text-white'
                        }`}
                      >
                        {u.role === 'user' ? 'Promote to Admin' : 'Demote to User'}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Desktop table view */}
          {!usersLoading && users && users.length > 0 && (
            <div className="hidden md:block bg-slate-800 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Username</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Role</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">First Login</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Last Updated</th>
                    <th className="text-left px-4 py-3 text-sm text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u: any) => {
                    const isSelf = u.user_id === currentUser?.id
                    return (
                      <tr key={u.user_id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                        <td className="px-4 py-3 text-white text-sm">
                          {u.username}
                          {isSelf && (
                            <span className="ml-2 text-xs text-slate-500">(you)</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`text-xs px-2 py-1 rounded font-medium ${
                              u.role === 'admin'
                                ? 'bg-purple-600/30 text-purple-300'
                                : 'bg-slate-600/30 text-slate-300'
                            }`}
                          >
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-sm">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-sm">
                          {new Date(u.updated_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3">
                          {isSelf ? (
                            <span className="text-xs text-slate-500">-</span>
                          ) : u.role === 'user' ? (
                            <button
                              onClick={() => roleMutation.mutate({ userId: u.user_id, role: 'admin' })}
                              disabled={roleMutation.isPending}
                              className="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                            >
                              Promote to Admin
                            </button>
                          ) : (
                            <button
                              onClick={() => roleMutation.mutate({ userId: u.user_id, role: 'user' })}
                              disabled={roleMutation.isPending}
                              className="bg-slate-600 hover:bg-slate-500 disabled:opacity-50 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
                            >
                              Demote to User
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {roleMutation.isError && (
            <p className="text-red-400 text-sm mt-4">
              {(roleMutation.error as any)?.response?.data?.detail || 'Failed to update role'}
            </p>
          )}
        </div>
      )}

      {/* ========== HEALTH TAB ========== */}
      {tab === 'health' && (
        <div className="max-w-lg space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-slate-400 text-sm">Service connectivity status. Auto-refreshes every 30s.</p>
            <button
              onClick={() => refetchHealth()}
              className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              Refresh
            </button>
          </div>

          {healthLoading && <p className="text-slate-400">Checking services...</p>}

          {!healthLoading && healthData && (
            <div className="space-y-3">
              {/* Jellyfin */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.jellyfin?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">Jellyfin</h3>
                </div>
                {healthData.jellyfin?.status === 'ok' ? (
                  <div className="ml-6 space-y-2">
                    <div className="space-y-1">
                      <p className="text-sm text-slate-300">{healthData.jellyfin.server_name}</p>
                      <p className="text-xs text-slate-400">Version {healthData.jellyfin.version}</p>
                      <p className="text-xs text-slate-500">{healthData.jellyfin.url}</p>
                    </div>
                    <button
                      onClick={() => scanMutation.mutate()}
                      disabled={scanMutation.isPending}
                      className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-1.5 rounded text-xs font-medium transition-colors"
                    >
                      {scanMutation.isPending ? 'Scanning...' : 'Scan Library'}
                    </button>
                    {scanMutation.isSuccess && (
                      <p className="text-green-400 text-xs">Library scan started.</p>
                    )}
                    {scanMutation.isError && (
                      <p className="text-red-400 text-xs">
                        {(scanMutation.error as any)?.response?.data?.detail || 'Failed to start scan'}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="ml-6">
                    <p className="text-sm text-red-400">Unreachable</p>
                    <p className="text-xs text-slate-500">{healthData.jellyfin?.url}</p>
                    {healthData.jellyfin?.detail && (
                      <p className="text-xs text-slate-500 mt-1">{healthData.jellyfin.detail}</p>
                    )}
                  </div>
                )}
              </div>

              {/* TMDB */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.tmdb?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">TMDB API</h3>
                </div>
                <div className="ml-6">
                  <p className="text-sm text-slate-300">
                    {healthData.tmdb?.status === 'ok' ? 'Connected' : 'Unreachable'}
                  </p>
                  {healthData.tmdb?.detail && (
                    <p className="text-xs text-slate-500 mt-1">{healthData.tmdb.detail}</p>
                  )}
                </div>
              </div>

              {/* Database */}
              <div className="bg-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-3 mb-2">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
                    healthData.database?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <h3 className="text-white font-medium">Database</h3>
                </div>
                <div className="ml-6">
                  <p className="text-sm text-slate-300">
                    {healthData.database?.status === 'ok' ? 'Connected' : 'Error'}
                  </p>
                  {healthData.database?.detail && (
                    <p className="text-xs text-slate-500 mt-1">{healthData.database.detail}</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========== TUNNEL TAB ========== */}
      {tab === 'tunnel' && (
        <div className="max-w-lg">
          <p className="text-slate-400 text-sm mb-6">
            Expose the app to the internet via an ngrok tunnel. Requires an ngrok authtoken configured in the backend <code className="text-slate-300">.env</code> file.
          </p>

          {tunnelLoading && <p className="text-slate-400">Checking tunnel status...</p>}

          {!tunnelLoading && tunnelData && (
            <div className="bg-slate-800 rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div
                  className={`w-3 h-3 rounded-full ${
                    tunnelData.active ? 'bg-green-500 animate-pulse' : 'bg-slate-600'
                  }`}
                />
                <span className="text-white font-medium">
                  {tunnelData.active ? 'Tunnel Active' : 'Tunnel Inactive'}
                </span>
              </div>

              {tunnelData.active && tunnelData.url && (
                <div className="bg-slate-700 rounded-lg p-4">
                  <p className="text-xs text-slate-400 mb-1">Public URL</p>
                  <a
                    href={tunnelData.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 text-sm break-all"
                  >
                    {tunnelData.url}
                  </a>
                  <button
                    onClick={() => navigator.clipboard.writeText(tunnelData.url!)}
                    className="ml-3 text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Copy
                  </button>
                </div>
              )}

              <div className="flex gap-3">
                {!tunnelData.active ? (
                  <button
                    onClick={() => startTunnelMutation.mutate()}
                    disabled={startTunnelMutation.isPending}
                    className="bg-green-600 hover:bg-green-700 disabled:bg-green-800 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    {startTunnelMutation.isPending ? 'Starting...' : 'Start Tunnel'}
                  </button>
                ) : (
                  <button
                    onClick={() => stopTunnelMutation.mutate()}
                    disabled={stopTunnelMutation.isPending}
                    className="bg-red-600 hover:bg-red-700 disabled:bg-red-800 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    {stopTunnelMutation.isPending ? 'Stopping...' : 'Stop Tunnel'}
                  </button>
                )}
              </div>

              {startTunnelMutation.isError && (
                <p className="text-red-400 text-sm">
                  {(startTunnelMutation.error as any)?.response?.data?.detail || 'Failed to start tunnel'}
                </p>
              )}
              {stopTunnelMutation.isError && (
                <p className="text-red-400 text-sm">
                  {(stopTunnelMutation.error as any)?.response?.data?.detail || 'Failed to stop tunnel'}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Backlog Note Modal */}
      {blNoteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-white mb-1">Update Backlog Item</h3>
            <p className="text-sm text-slate-400 mb-4">
              Moving to <span className="font-medium text-white capitalize">{blNoteModal.status.replace('_', ' ')}</span>. Add an optional note:
            </p>
            <textarea
              value={blNoteText}
              onChange={(e) => setBlNoteText(e.target.value)}
              placeholder="Optional note..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setBlNoteModal(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmBacklogMove}
                disabled={backlogMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-sm rounded-lg font-medium transition-colors"
              >
                {backlogMutation.isPending ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Blocker Modal */}
      {blockerModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Set request blocker</h3>
              <p className="text-sm text-slate-400">Make the queue honest about why <span className="text-white">{blockerModal.title}</span> is paused and when it gets re-checked.</p>
            </div>
            <label className="block text-sm text-slate-300">Reason
              <input
                value={blockerReason}
                onChange={(e) => setBlockerReason(e.target.value)}
                placeholder="Waiting for upstream release"
                className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-white"
              />
            </label>
            <label className="block text-sm text-slate-300">Review date
              <input
                type="date"
                value={blockerReviewOn}
                onChange={(e) => setBlockerReviewOn(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-white"
              />
            </label>
            <label className="block text-sm text-slate-300">Requester-visible note
              <textarea
                value={blockerNote}
                onChange={(e) => setBlockerNote(e.target.value)}
                rows={3}
                placeholder="Optional detail so they do not have to ask what is going on."
                className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-white placeholder-slate-400"
              />
            </label>
            <div className="flex justify-between gap-3">
              <button onClick={() => { setBlockerModal(null); setBlockerReason(''); setBlockerNote(''); setBlockerReviewOn('') }} className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200">Cancel</button>
              <button onClick={saveBlocker} disabled={!blockerReason.trim() || !blockerReviewOn || blockerMutation.isPending} className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-medium">
                {blockerMutation.isPending ? 'Saving...' : 'Save blocker'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Note Modal */}
      {noteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-white mb-1">Move Request</h3>
            <p className="text-sm text-slate-400 mb-4">
              Changing status to <span className="font-medium text-white capitalize">{noteModal.status}</span>. Add an optional note:
            </p>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Optional note for the user..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => setNoteModal(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmMove}
                disabled={updateMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-sm rounded-lg font-medium transition-colors"
              >
                {updateMutation.isPending ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
