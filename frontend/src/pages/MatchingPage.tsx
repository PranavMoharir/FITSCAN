// Matching: how scores are computed, the latest match run (live while it runs), recomputing, and a
// quick way to open any candidate's or job's top matches. Uses only existing endpoints.

import { ArrowRight, Briefcase, Gauge, MapPin, Search, Sparkles, Target, Users } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { getMatchWeights, listBackgroundJobs, searchCandidates, searchJobs } from '@/api/client'
import { noun, progressText } from '@/components/app/job-text'
import { PageHeader } from '@/components/app/PageHeader'
import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { Segmented } from '@/components/app/Segmented'
import { EmptyState, ErrorNotice, ListSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/StatusBadge'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { useToast } from '@/components/app/toaster'
import { RecomputeMatchesDialog } from '@/components/background-jobs/actions'
import { sameWeights, WEIGHT_PARTS, weightsText } from '@/components/matches/WeightsEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useDebouncedParam } from '@/hooks/useDebouncedParam'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'
import { useResource } from '@/hooks/useResource'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { formatNumber, isActive, shortId } from '@/lib/format'
import type { MatchWeightsInfo } from '@/types/api'

const DIMENSIONS = [
  { icon: Sparkles, letter: 'R', key: 'required', title: 'Required skills', text: 'The share of the job’s must-have skills the candidate has.' },
  { icon: Gauge, letter: 'N', key: 'nice', title: 'Nice-to-have skills', text: 'The share of the preferred skills the candidate brings.' },
  { icon: Briefcase, letter: 'E', key: 'experience', title: 'Experience', text: 'Years of experience against the job’s stated minimum.' },
  { icon: MapPin, letter: 'L', key: 'location', title: 'Location', text: 'Same city, or a remote role.' },
] as const

async function loadRuns(signal: AbortSignal) {
  const [latest, completed, jobs, candidates] = await Promise.all([
    listBackgroundJobs({ type: 'match', page_size: 1 }, signal),
    listBackgroundJobs({ type: 'match', status: 'completed', page_size: 1 }, signal),
    searchJobs({ page_size: 1 }, signal),
    searchCandidates({ page_size: 1 }, signal),
  ])
  return { latest: latest.items[0] ?? null, lastCompleted: completed.items[0] ?? null, runs: latest.total, jobs: jobs.total, candidates: candidates.total }
}

function LastRun({ onRecompute, onRunEnded }: { onRecompute: () => void; onRunEnded: () => void }) {
  const runs = useResource(loadRuns, [])
  const latest = runs.data?.latest
  const live = latest ? isActive(latest.status) : false
  usePolling(runs.reload, POLL_INTERVAL_MS, live)
  useReloadWhenHealthy(runs.reload, Boolean(runs.error))
  // A run that ends while the page is open can change which weights the current matches used.
  const wasLive = useRef(false)
  useEffect(() => {
    if (wasLive.current && !live) onRunEnded()
    wasLive.current = live
  }, [live, onRunEnded])

  const d = runs.data
  return (
    <Panel id="last-run" title="Match runs" description="Matches are stored by the last completed run and shown on every job and candidate page.">
      {runs.error && !d ? (
        <ErrorNotice error={runs.error} onRetry={() => void runs.reload()} />
      ) : !d ? (
        <ListSkeleton rows={2} />
      ) : !latest ? (
        <EmptyState
          compact
          icon={Target}
          title="No match run yet"
          description="Recompute matches to score every candidate against every job."
          action={<Button onClick={onRecompute}>Recompute matches</Button>}
        />
      ) : (
        <div className="grid gap-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-subtle-foreground">Latest run</p>
              <p className="mt-1 flex flex-wrap items-center gap-2">
                <Link to={`/background-jobs/${latest.background_job_id}`} className="rounded text-sm font-semibold text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
                  Match run, <RelativeTime value={latest.created_at} />
                </Link>
                <StatusBadge status={latest.status} />
              </p>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/background-jobs?type=match">
                All {formatNumber(d.runs)} runs
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          </div>
          {live ? (
            <div>
              <Progress value={latest.status === 'queued' ? 0 : latest.progress.total ? latest.progress.percent : null} aria-label="Match run progress" />
              <p className="mt-2 text-[13px] tabular-nums text-muted-foreground">{progressText(latest)}. The current matches stay until it finishes.</p>
            </div>
          ) : null}
          <dl className="grid gap-4 border-t border-border pt-5 sm:grid-cols-3">
            <div>
              <dt className="text-[13px] text-muted-foreground">Current matches from</dt>
              <dd className="mt-1 text-sm font-medium text-foreground">{d.lastCompleted ? <RelativeTime value={d.lastCompleted.finished_at} /> : 'No completed run'}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted-foreground">Scored in that run</dt>
              <dd className="mt-1 text-sm font-medium text-foreground">{d.lastCompleted ? noun(d.lastCompleted, d.lastCompleted.items_succeeded) : '—'}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted-foreground">A new run would score</dt>
              <dd className="mt-1 text-sm font-medium text-foreground">
                {formatNumber(d.candidates)} × {formatNumber(d.jobs)} = {formatNumber(d.candidates * d.jobs)} pairs
              </dd>
            </div>
          </dl>
        </div>
      )}
    </Panel>
  )
}

/** Where the active weights come from, and what the stored results were computed with when that differs. */
function WeightsSource({ info }: { info: MatchWeightsInfo }) {
  const { active, results } = info
  const fromRun = active.source === 'match_run' && active.background_job_id
  return (
    <div className="mt-3 grid gap-1.5 text-[13px] leading-relaxed text-muted-foreground">
      <p>
        {fromRun ? (
          <>
            Active weights, chosen for{' '}
            <Link to={`/background-jobs/${active.background_job_id}`} className="rounded font-medium text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
              run #{shortId(active.background_job_id!)}
            </Link>
            .{' '}
          </>
        ) : (
          'Active weights: the defaults. '
        )}
        {sameWeights(active.weights, info.default) ? (fromRun ? 'They are the defaults.' : '') : `The defaults are ${weightsText(info.default)}.`}
      </p>
      {results && !results.weights ? (
        <p>The current matches are from a run before weights were recorded (weights not recorded).</p>
      ) : results?.weights && !sameWeights(results.weights, active.weights) ? (
        <p>The current matches were computed with {weightsText(results.weights)}.</p>
      ) : null}
    </div>
  )
}

function Formula({ refresh }: { refresh: number }) {
  const weights = useResource(getMatchWeights, [refresh])
  useReloadWhenHealthy(weights.reload, Boolean(weights.error))
  const info = weights.data
  const w = info?.active.weights
  return (
    <Panel id="formula" title="How a score is computed" description="Every candidate is scored against every job with one weighted formula.">
      {weights.error && !info ? (
        <ErrorNotice error={weights.error} onRetry={() => void weights.reload()} />
      ) : !w || !info ? (
        <Skeleton className="h-11 rounded-lg" />
      ) : (
        <>
          <p className="rounded-lg bg-foreground/[0.03] px-4 py-3 font-mono text-[13px] text-foreground">
            Score = {WEIGHT_PARTS.map((p) => `${formatNumber(w[p.key])}${p.letter}`).join(' + ')}
          </p>
          <WeightsSource info={info} />
        </>
      )}
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {DIMENSIONS.map((d) => (
          <li key={d.letter} className="flex gap-3 rounded-lg p-1">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink" aria-hidden="true">
              <d.icon className="size-4" />
            </span>
            <div>
              <p className="text-sm font-medium text-foreground">
                {d.title}{' '}
                <span className="font-mono text-xs text-subtle-foreground">
                  ({d.letter}
                  {w ? `, up to ${formatNumber(w[d.key])}` : ''})
                </span>
              </p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{d.text}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-subtle-foreground">
        Each part is a fraction from 0 to 1. The weights are whole numbers that add up to 100; choose them when you recompute matches, and each run records the weights it used. Each match’s breakdown shows the points it actually received. Text similarity is used only to order exact-score ties; it never changes a score.
      </p>
    </Panel>
  )
}

type Side = 'candidates' | 'jobs'

function Lookup() {
  const [side, setSide] = useState<Side>('candidates')
  const [term, setTerm] = useState('')
  const [draft, setDraft] = useDebouncedParam(term, setTerm)
  const results = useResource(
    async (signal) => {
      if (side === 'candidates') {
        const page = await searchCandidates({ q: term || undefined, page_size: 6 }, signal)
        return { total: page.total, items: page.items.map((c) => ({ id: c.candidate_id, to: `/candidates/${c.candidate_id}`, title: c.name ?? 'Unnamed candidate', subtitle: [c.current_title, c.city].filter(Boolean).join(' · ') })) }
      }
      const page = await searchJobs({ q: term || undefined, page_size: 6 }, signal)
      return { total: page.total, items: page.items.map((j) => ({ id: j.job_id, to: `/jobs/${j.job_id}`, title: j.title, subtitle: [j.company, j.location].filter(Boolean).join(' · ') })) }
    },
    [side, term],
  )
  return (
    <Panel id="lookup" title="Look up matches" description="Open a candidate to see their top jobs, or a job to see its top candidates.">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          label="Look up"
          value={side}
          options={[
            { value: 'candidates', label: 'Candidates' },
            { value: 'jobs', label: 'Jobs' },
          ]}
          onChange={(v) => setSide(v)}
        />
        <div className="relative min-w-[12rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle-foreground" aria-hidden="true" />
          <Input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={side === 'candidates' ? 'Name or current title' : 'Title or company'}
            aria-label={side === 'candidates' ? 'Search candidates by name or current title' : 'Search jobs by title or company'}
            className="pl-9"
          />
        </div>
      </div>
      <div className="mt-4" aria-busy={results.refreshing}>
        {results.error ? (
          <ErrorNotice error={results.error} onRetry={() => void results.reload()} />
        ) : !results.data ? (
          <ListSkeleton rows={3} />
        ) : results.data.items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{term ? `No ${side} match “${term}”.` : `No ${side} yet.`}</p>
        ) : (
          <>
            <ul className="divide-y divide-border">
              {results.data.items.map((r) => (
                <li key={r.id}>
                  <Link to={r.to} className="group -mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 outline-none transition-colors hover:bg-foreground/[0.03] focus-visible:ring-3 focus-visible:ring-ring/50">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink" aria-hidden="true">
                      {side === 'candidates' ? <Users className="size-4" /> : <Briefcase className="size-4" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-foreground">{r.title}</span>
                      {r.subtitle && <span className="block truncate text-xs text-subtle-foreground">{r.subtitle}</span>}
                    </span>
                    <ArrowRight className="size-4 text-subtle-foreground transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
            {results.data.total > results.data.items.length && (
              <Link
                to={side === 'candidates' ? `/candidates${term ? `?q=${encodeURIComponent(term)}` : ''}` : `/jobs${term ? `?q=${encodeURIComponent(term)}` : ''}`}
                className="mt-3 inline-flex rounded text-[13px] font-medium text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                See all {formatNumber(results.data.total)} {side}
              </Link>
            )}
          </>
        )}
      </div>
    </Panel>
  )
}

export default function MatchingPage() {
  useDocumentTitle('Matching')
  const navigate = useNavigate()
  const toast = useToast()
  const [recompute, setRecompute] = useState(false)
  const [key, setKey] = useState(0)
  const [runsEnded, setRunsEnded] = useState(0)
  const onRunEnded = useCallback(() => setRunsEnded((n) => n + 1), [])
  return (
    <>
      <PageHeader
        title="Matching"
        description="How every candidate is scored against every job, and the latest match run."
        actions={
          <Button onClick={() => setRecompute(true)}>
            <Target aria-hidden="true" />
            Recompute matches
          </Button>
        }
      />
      <div className="grid items-start gap-4 lg:grid-cols-5 lg:gap-5">
        <div className="grid gap-4 lg:col-span-3 lg:gap-5">
          <LastRun key={key} onRecompute={() => setRecompute(true)} onRunEnded={onRunEnded} />
          <Formula key={key} refresh={runsEnded} />
        </div>
        <div className="lg:col-span-2">
          <Lookup />
        </div>
      </div>
      <RecomputeMatchesDialog
        open={recompute}
        onOpenChange={setRecompute}
        onCreated={(job) => {
          setRecompute(false)
          setKey((k) => k + 1)
          toast({ title: 'Match run queued', description: 'It starts as soon as a worker is free.', action: { label: 'View the run', onClick: () => navigate(`/background-jobs/${job.background_job_id}`) } })
        }}
      />
    </>
  )
}
