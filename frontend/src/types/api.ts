// TypeScript types that mirror the API's Pydantic schemas (backend/app/schemas).
// Field names and nullability follow the schemas exactly; keep them in step when a schema changes.

/** Error envelope returned by every failed request (HLD §12.1). */
export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody
}

/** One entry of `details.errors` on a 422 VALIDATION_ERROR (backend/app/errors.py). */
export interface FieldError {
  field: string
  message: string
}

/** Every paginated list (LLD §4.4). */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type SortOrder = 'asc' | 'desc'
export type ExportFormat = 'csv' | 'json'

// --- GET /health (schemas/health.py) ------------------------------------------------------------

export type CheckStatus = 'ok' | 'down'

export interface HealthResponse {
  status: 'ok'
  database: CheckStatus
  redis: CheckStatus
}

// --- /background-jobs (schemas/background_job.py) -----------------------------------------------

export type BackgroundJobType = 'crawl' | 'resume' | 'match'
export type BackgroundJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export interface Progress {
  current: number
  /** null while the total is not known yet. */
  total: number | null
  percent: number
}

export interface BackgroundJobCreated {
  background_job_id: string
  type: BackgroundJobType
  status: BackgroundJobStatus
  progress: Progress
  created_at: string
}

export interface AcceptedFileInfo {
  index: number
  upload_id: string
  size_bytes: number
}

export interface RejectedFileInfo {
  index: number
  code: 'FILE_TOO_LARGE' | 'NOT_A_PDF'
  message: string
}

export interface ResumeJobCreated extends BackgroundJobCreated {
  accepted_files: AcceptedFileInfo[]
  rejected_files: RejectedFileInfo[]
}

export interface BackgroundJobSummary extends BackgroundJobCreated {
  items_succeeded: number
  items_failed: number
  started_at: string | null
  finished_at: string | null
}

export interface BackgroundJobDetail extends BackgroundJobSummary {
  params: Record<string, unknown> | null
  error_message: string | null
}

export type BackgroundJobList = Page<BackgroundJobSummary>

export interface CrawlRequest {
  seed_url: string
  max_depth: number
  max_pages: number
  allowed_domains?: string[] | null
}

export interface CancelResult {
  status: BackgroundJobStatus
  cancel_requested?: boolean
}

export interface LogLine {
  log_id: number
  created_at: string
  level: LogLevel
  message: string
  context?: Record<string, unknown> | null
}

export interface LogList {
  items: LogLine[]
  next_after_id: number
}

// --- /jobs (schemas/job.py) ---------------------------------------------------------------------

export type JobType = 'full_time' | 'part_time' | 'contract' | 'internship' | 'temporary' | 'unknown'

export interface Salary {
  min: number | null
  max: number | null
  currency: string | null
  period: string | null
}

export interface JobSummary {
  job_id: string
  title: string
  company: string | null
  location: string | null
  job_type: JobType
  salary: Salary | null
  posted_date: string | null
  required_skills: string[]
  nice_to_have_skills: string[]
  min_experience_years: number | null
  apply_url: string
  source: string
}

export interface JobDetail extends JobSummary {
  is_remote: boolean
  description: string | null
  salary_text: string | null
  source_url: string | null
  created_at: string
  updated_at: string
}

export type JobList = Page<JobSummary>

export type JobSort = 'posted_date' | 'title'

export interface JobFilters {
  q?: string
  skill?: string
  location?: string
  job_type?: JobType
  max_required_years?: number
  sort?: JobSort
  order?: SortOrder
}

// --- /candidates (schemas/candidate.py) ---------------------------------------------------------

export interface EducationEntry {
  degree: string | null
  institution: string | null
  years: string | null
}

export interface CandidateSummary {
  candidate_id: string
  name: string | null
  email: string | null
  phone: string | null
  city: string | null
  current_title: string | null
  skills: string[]
  years_experience: number | null
  education: EducationEntry[]
  summary: string | null
  source_file: string
  parsed_with_ocr: boolean
}

export interface CandidateDetail extends CandidateSummary {
  parse_warnings: string[]
  created_at: string
  updated_at: string
}

export type CandidateList = Page<CandidateSummary>

export type CandidateSort = 'name' | 'years_experience'

export interface CandidateFilters {
  q?: string
  skill?: string
  city?: string
  sort?: CandidateSort
  order?: SortOrder
}

// --- /skills (schemas/skill.py) -----------------------------------------------------------------

export interface SkillItem {
  skill: string
  category: string | null
}

export type SkillList = Page<SkillItem>

// --- Matches (schemas/match.py) -----------------------------------------------------------------

export type SkillLevel = 'required' | 'nice_to_have'

export interface SkillRef {
  skill: string
  level: SkillLevel
}

export type SkillRule = 'ratio' | 'none_listed' | 'no_required_identified' | 'no_skills_identified'
export type ExperienceRule = 'ratio' | 'no_minimum' | 'years_unknown'
export type LocationRule = 'remote' | 'same_city' | 'different_city' | 'candidate_city_unknown' | 'job_city_unknown'

export interface SkillComponent {
  matched: number
  total: number
  ratio: number
  points: number
  rule: SkillRule
}

export interface ExperienceComponent {
  candidate_years: number | null
  minimum: number | null
  fit: number
  points: number
  rule: ExperienceRule
}

export interface LocationComponent {
  candidate_city: string | null
  job_location: string | null
  job_city: string | null
  fit: number
  points: number
  rule: LocationRule
}

export interface Breakdown {
  required: SkillComponent
  nice_to_have: SkillComponent
  experience: ExperienceComponent
  location: LocationComponent
}

interface MatchBase {
  rank: number
  score: number
  matched_skills: SkillRef[]
  missing_skills: SkillRef[]
  breakdown: Breakdown
  /** TF-IDF cosine similarity; only orders equal scores. */
  text_similarity: number | null
  explanation: string
}

/** One of a candidate's top jobs. */
export interface JobMatch extends MatchBase {
  job_id: string
  title: string
  company: string | null
}

/** One of a job's top candidates. */
export interface CandidateMatch extends MatchBase {
  candidate_id: string
  name: string | null
  current_title: string | null
  city: string | null
}

export interface CandidateMatches {
  candidate_id: string
  /** null when no match run has included this candidate. */
  computed_at: string | null
  items: JobMatch[]
}

export interface JobMatches {
  job_id: string
  computed_at: string | null
  items: CandidateMatch[]
}

// --- Scoring weights (GET /matching/weights, LLD §7.4) ----------------------------------------------

/** Weights of the four score components; they add up to 100. */
export interface MatchWeights {
  required: number
  nice: number
  experience: number
  location: number
}

export interface MatchWeightsInfo {
  /** MATCH_WEIGHTS: 70, 15, 10, 5 unless the server is configured otherwise. */
  default: MatchWeights
  /** What a run started without weights uses: the latest queued, running or completed run's, else the default. */
  active: { weights: MatchWeights; source: 'match_run' | 'default'; background_job_id: string | null }
  /** The run whose results are stored; weights null when it is from before weights were recorded. */
  results: { background_job_id: string; weights: MatchWeights | null } | null
}
