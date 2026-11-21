// Skills: the canonical skill list from GET /skills, grouped by category, with links that filter the
// Jobs and Candidates pages by each skill.

import { Briefcase, Search, Tags, Users, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'

import { listSkills } from '@/api/client'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorNotice } from '@/components/app/states'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useResource } from '@/hooks/useResource'
import { formatNumber, plural } from '@/lib/format'

const OTHER = 'Other'
const title = (category: string) => category.replace(/[_-]+/g, ' ').replace(/^./, (c) => c.toUpperCase())

function SkillLink({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Briefcase }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="ghost" size="icon-xs">
          <Link to={to} aria-label={label}>
            <Icon aria-hidden="true" />
          </Link>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

export default function SkillsPage() {
  useDocumentTitle('Skills')
  const skills = useResource(listSkills, [])
  useReloadWhenHealthy(skills.reload, Boolean(skills.error))
  const [term, setTerm] = useState('')
  const [category, setCategory] = useState('all')

  const groups = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const s of skills.data?.items ?? []) {
      const key = s.category ?? OTHER
      map.set(key, [...(map.get(key) ?? []), s.skill])
    }
    return [...map.entries()].sort(([a], [b]) => (a === OTHER ? 1 : b === OTHER ? -1 : a.localeCompare(b)))
  }, [skills.data])

  const needle = term.trim().toLowerCase()
  const visible = groups
    .filter(([key]) => category === 'all' || key === category)
    .map(([key, names]) => [key, names.filter((n) => n.toLowerCase().includes(needle))] as const)
    .filter(([, names]) => names.length > 0)
  const shown = visible.reduce((n, [, names]) => n + names.length, 0)

  return (
    <>
      <PageHeader
        title="Skills"
        description="The canonical skills that job and candidate skills are normalised to. Skill filters accept these names and their common aliases."
      />
      {skills.error && !skills.data ? (
        <ErrorNotice block error={skills.error} onRetry={() => void skills.reload()} retrying={skills.refreshing} />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[14rem] flex-1 sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle-foreground" aria-hidden="true" />
              <Input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Find a skill" aria-label="Find a skill" className="pl-9" />
            </div>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="h-9 w-[13rem] rounded-full" aria-label="Category">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {groups.map(([key, names]) => (
                  <SelectItem key={key} value={key}>
                    {title(key)} ({names.length})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(term || category !== 'all') && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setTerm('')
                  setCategory('all')
                }}
              >
                <X aria-hidden="true" />
                Clear
              </Button>
            )}
            {skills.data && (
              <p className="ml-auto text-[13px] text-muted-foreground" aria-live="polite">
                {shown === skills.data.total ? `${plural(skills.data.total, 'skill')} in ${plural(groups.length, 'category', 'categories')}` : `${formatNumber(shown)} of ${formatNumber(skills.data.total)} skills`}
              </p>
            )}
          </div>
          <Card className="gap-0 py-0" aria-busy={skills.loading}>
            {skills.loading ? (
              <div className="grid gap-6 p-5 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading skills">
                {Array.from({ length: 9 }, (_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : skills.data?.total === 0 ? (
              <EmptyState icon={Tags} title="No skills loaded" description="The worker loads the skill list from taxonomy.json when it starts. Start the worker, then refresh." />
            ) : visible.length === 0 ? (
              <EmptyState icon={Search} title={`No skill matches “${term}”`} description="Try part of the name, for example “script” or “sql”." />
            ) : (
              <div className="divide-y divide-border">
                {visible.map(([key, names]) => (
                  <section key={key} aria-labelledby={`cat-${key}`} className="px-5 py-5">
                    <h2 id={`cat-${key}`} className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle-foreground">
                      {title(key)}
                      <span className="font-medium normal-case tracking-normal">{names.length}</span>
                    </h2>
                    <ul className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-2 xl:grid-cols-3">
                      {names.map((name) => (
                        <li key={name} className="group -mx-2 flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-foreground/[0.03]">
                          <span className="truncate text-sm font-medium text-foreground">{name}</span>
                          <span className="flex shrink-0 items-center gap-0.5">
                            <SkillLink to={`/jobs?skill=${encodeURIComponent(name)}`} label={`Jobs that ask for ${name}`} icon={Briefcase} />
                            <SkillLink to={`/candidates?skill=${encodeURIComponent(name)}`} label={`Candidates with ${name}`} icon={Users} />
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </>
  )
}
