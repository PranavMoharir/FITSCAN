// Synthetic demonstration data for the landing page. These people, companies and jobs are
// invented; nothing here comes from the API or the database.
//
// `demoScore` follows the documented formula (Score = 70R + 15N + 10E + 5L, HLD §10, ADR-016/017)
// only so that the illustrative numbers add up. Real scores are computed by the backend.

export interface DemoCandidate {
  id: string
  name: string
  initials: string
  title: string
  city: string
  years: number
  education: string
  skills: string[]
  source: string
}

export interface DemoJob {
  id: string
  title: string
  company: string
  city: string | null
  remote: boolean
  jobType: string
  minYears: number | null
  required: string[]
  niceToHave: string[]
}

export interface DemoPart {
  fit: number
  points: number
}

export interface DemoMatch {
  candidate: DemoCandidate
  job: DemoJob
  score: number
  required: DemoPart & { matched: string[]; missing: string[] }
  nice: DemoPart & { matched: string[]; missing: string[] }
  experience: DemoPart
  location: DemoPart & { reason: string }
  explanation: string
}

export const WEIGHTS = { required: 70, nice: 15, experience: 10, location: 5 } as const

export const demoJobs: DemoJob[] = [
  {
    id: 'job-1',
    title: 'Senior Python Developer',
    company: 'Orbitline Systems',
    city: 'Pune',
    remote: false,
    jobType: 'Full-time',
    minYears: 5,
    required: ['Python', 'Django', 'PostgreSQL', 'REST APIs', 'Docker'],
    niceToHave: ['Redis', 'Celery', 'AWS', 'Kubernetes', 'GraphQL'],
  },
  {
    id: 'job-2',
    title: 'Data Engineer',
    company: 'Kestrel Analytics',
    city: 'Bengaluru',
    remote: false,
    jobType: 'Full-time',
    minYears: 3,
    required: ['Python', 'SQL', 'Apache Spark', 'Airflow'],
    niceToHave: ['AWS', 'Docker', 'Kafka'],
  },
  {
    id: 'job-3',
    title: 'Frontend Developer',
    company: 'Brightwave Labs',
    city: null,
    remote: true,
    jobType: 'Full-time',
    minYears: 2,
    required: ['JavaScript', 'TypeScript', 'React', 'CSS'],
    niceToHave: ['Next.js', 'Testing Library', 'GraphQL'],
  },
  {
    id: 'job-4',
    title: 'Machine Learning Engineer',
    company: 'Halcyon Research',
    city: 'Hyderabad',
    remote: false,
    jobType: 'Full-time',
    minYears: 4,
    required: ['Python', 'PyTorch', 'scikit-learn', 'SQL'],
    niceToHave: ['Docker', 'MLflow', 'AWS'],
  },
]

export const demoCandidates: DemoCandidate[] = [
  {
    id: 'cand-1',
    name: 'Ananya Rao',
    initials: 'AR',
    title: 'Backend Engineer',
    city: 'Pune',
    years: 4,
    education: 'B.E. Computer Engineering',
    skills: ['Python', 'Django', 'PostgreSQL', 'REST APIs', 'Docker', 'Redis', 'Celery', 'AWS', 'Git'],
    source: 'PDF · text layer',
  },
  {
    id: 'cand-2',
    name: 'Rohan Mehta',
    initials: 'RM',
    title: 'Data Engineer',
    city: 'Bengaluru',
    years: 5,
    education: 'M.Sc. Data Science',
    skills: ['Python', 'SQL', 'Apache Spark', 'Airflow', 'Kafka', 'Docker', 'PostgreSQL'],
    source: 'PDF · text layer',
  },
  {
    id: 'cand-3',
    name: 'Sara Thomas',
    initials: 'ST',
    title: 'Frontend Developer',
    city: 'Kochi',
    years: 3,
    education: 'B.Tech Information Technology',
    skills: ['JavaScript', 'TypeScript', 'React', 'CSS', 'Next.js', 'Figma'],
    source: 'PDF · OCR (scanned)',
  },
  {
    id: 'cand-4',
    name: 'Vikram Iyer',
    initials: 'VI',
    title: 'ML Engineer',
    city: 'Chennai',
    years: 3,
    education: 'M.Tech Artificial Intelligence',
    skills: ['Python', 'PyTorch', 'scikit-learn', 'Docker', 'Pandas'],
    source: 'PDF · text layer',
  },
]

/** The pair shown in the hero: 70·1 + 15·(3/5) + 10·1 + 5·1 = 94. */
export const heroCandidate: DemoCandidate = {
  id: 'hero-candidate',
  name: 'Priya Nair',
  initials: 'PN',
  title: 'Backend Engineer',
  city: 'Pune',
  years: 6,
  education: 'B.Tech Computer Science',
  skills: ['Python', 'Django', 'PostgreSQL', 'REST APIs', 'Docker', 'Redis', 'Celery', 'AWS'],
  source: 'PDF · text layer',
}

export const heroJob: DemoJob = { ...demoJobs[0], id: 'hero-job', city: null, remote: true }

function split(wanted: string[], has: Set<string>) {
  return { matched: wanted.filter((s) => has.has(s)), missing: wanted.filter((s) => !has.has(s)) }
}

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function demoMatch(candidate: DemoCandidate, job: DemoJob): DemoMatch {
  const has = new Set(candidate.skills)
  const req = split(job.required, has)
  const nice = split(job.niceToHave, has)
  const noSkills = job.required.length === 0 && job.niceToHave.length === 0

  const r = noSkills || job.required.length === 0 ? 0 : req.matched.length / job.required.length
  const n = noSkills ? 0 : job.niceToHave.length === 0 ? 1 : nice.matched.length / job.niceToHave.length
  const e = job.minYears === null ? 1 : Math.min(1, candidate.years / job.minYears)
  const sameCity = job.city !== null && job.city.toLowerCase() === candidate.city.toLowerCase()
  const l = job.remote || sameCity ? 1 : 0
  const locationReason = job.remote ? 'Remote role' : sameCity ? `Same city (${candidate.city})` : `Different city (${candidate.city} vs ${job.city})`

  const parts = {
    required: { fit: r, points: WEIGHTS.required * r, ...req },
    nice: { fit: n, points: WEIGHTS.nice * n, ...nice },
    experience: { fit: e, points: WEIGHTS.experience * e },
    location: { fit: l, points: WEIGHTS.location * l, reason: locationReason },
  }
  const score = Math.min(100, parts.required.points + parts.nice.points + parts.experience.points + parts.location.points)

  const reqText =
    req.missing.length === 0
      ? `Has all ${plural(job.required.length, 'required skill')}`
      : `Has ${req.matched.length} of ${plural(job.required.length, 'required skill')} (missing ${req.missing.join(', ')})`
  const niceText = job.niceToHave.length ? ` and ${nice.matched.length} of ${job.niceToHave.length} nice-to-have skills` : ''
  const expText =
    job.minYears === null
      ? 'No minimum experience.'
      : `${plural(candidate.years, 'year')} of experience against a ${job.minYears}-year minimum.`

  return { candidate, job, score, ...parts, explanation: `${reqText}${niceText}. ${expText} ${locationReason}.` }
}

/** All demo jobs for a candidate, best first (ties keep the list order). */
export function topJobsFor(candidate: DemoCandidate): DemoMatch[] {
  return demoJobs.map((job) => demoMatch(candidate, job)).sort((a, b) => b.score - a.score)
}

/** All demo candidates for a job, best first. */
export function topCandidatesFor(job: DemoJob): DemoMatch[] {
  return demoCandidates.map((candidate) => demoMatch(candidate, job)).sort((a, b) => b.score - a.score)
}

/** Scores are shown with two decimals, like the application (LLD §8.6). */
export const formatScore = (score: number) => score.toFixed(2)
export const formatPercent = (fit: number) => `${Math.round(fit * 100)}%`
