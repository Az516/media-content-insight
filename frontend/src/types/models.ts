/**
 * 共享 TypeScript 模型定义 (`frontend/src/types/models.ts`)。
 *
 * 字段命名严格对齐 `design.md` §3 中的 ER 图与 §3 REST API 响应结构,
 * 保持与后端 SQLAlchemy ORM / Pydantic schema 一致(snake_case)。
 */

// ────────────────────────────────────────────────────────────────────────────
// 任务 (Task)
// ────────────────────────────────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed';
export type PlatformKey = 'xhs' | 'dy' | 'ks' | 'bili' | 'wb' | 'tieba' | 'zhihu' | 'wechat';

/** 任务列表 item(`GET /api/tasks` 中的单元素)。 */
export interface TaskListItem {
  id: number;
  keyword: string;
  platform?: PlatformKey;
  status: TaskStatus;
  note_count: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

/** 任务详情 summary 字段中的作者条目。 */
export interface TopAuthor {
  user_id: string;
  nickname: string | null;
  note_count: number;
}

/** 任务详情 summary 字段。 */
export interface TaskSummary {
  total_likes: number;
  total_comments: number;
  top_authors: TopAuthor[];
}

/**
 * 内嵌在 `GET /api/tasks/{id}` 响应中的 AI 报告元数据,
 * 用于支撑需求 16.5 历史报告列表(避免新增独立路由违反需求 19.1)。
 */
export interface AIReportSummary {
  id: number;
  provider: AIProvider;
  model: string;
  prompt_version: string;
  created_at: string;
}

/** 任务详情(`GET /api/tasks/{id}`)。 */
export interface Task {
  id: number;
  keyword: string;
  platform: PlatformKey;
  status: TaskStatus;
  note_count: number;
  max_notes: number;
  started_at: string | null;
  finished_at: string | null;
  error_msg: string | null;
  json_path: string | null;
  created_at: string;
  summary: TaskSummary;
  reports: AIReportSummary[];
}

// ────────────────────────────────────────────────────────────────────────────
// 作者 (Author)
// ────────────────────────────────────────────────────────────────────────────

export interface Author {
  user_id: string;
  nickname: string | null;
  avatar: string | null;
  gender: string | null;
  ip_location: string | null;
  fans_count: number;
  follow_count: number;
}

// ────────────────────────────────────────────────────────────────────────────
// 笔记 (Note)
// ────────────────────────────────────────────────────────────────────────────

export type NoteType = 'normal' | 'video';

/** 笔记列表 item(`GET /api/tasks/{id}/notes` 中的单元素)。 */
export interface NoteSummary {
  note_id: string;
  title: string | null;
  type: NoteType | null;
  cover_url: string | null;
  liked_count: number;
  collected_count: number;
  comment_count: number;
  author: Pick<Author, 'user_id' | 'nickname'>;
}

/** 笔记详情(`GET /api/notes/{note_id}` 中的 `note` 字段)。 */
export interface Note {
  note_id: string;
  task_id?: number;
  title: string | null;
  desc: string | null;
  type: NoteType | null;
  cover_url: string | null;
  video_url: string | null;
  liked_count: number;
  collected_count: number;
  comment_count: number;
  share_count: number;
  author_user_id?: string;
  publish_time: string | null;
  ip_location: string | null;
  tag_list: string[] | null;
}

/** 笔记详情完整响应。 */
export interface NoteDetailResponse {
  note: Note;
  author: Author;
  comments: CommentNode[];
}

// ────────────────────────────────────────────────────────────────────────────
// 评论 (Comment / CommentNode)
// ────────────────────────────────────────────────────────────────────────────

/**
 * 评论(扁平记录,对应 `comments` 表)。
 *
 * 注意:`is_top_hot` 在 SQLite 中存为 INTEGER(0/1),为了减少前端体验抖动,
 * 这里保留 number(0|1)以保持与后端响应一致。
 */
export interface Comment {
  comment_id: string;
  note_id: string;
  parent_comment_id: string | null;
  user_id: string | null;
  nickname: string | null;
  content: string | null;
  like_count: number;
  sub_comment_count: number;
  create_time: string | null;
  is_top_hot: 0 | 1;
}

/**
 * 评论树节点(一级评论,内含 `sub_comments` 二级评论数组)。
 *
 * `sub_comments` 中的元素本身不再有更深一层 `sub_comments`(后端只返回二级)。
 */
export interface CommentNode extends Comment {
  sub_comments?: Comment[];
}

// ────────────────────────────────────────────────────────────────────────────
// 评论洞察聚合 (`GET /api/tasks/{id}/comments`)
// ────────────────────────────────────────────────────────────────────────────

export interface KeywordCount {
  word: string;
  count: number;
}

export interface SentimentDistribution {
  positive: number;
  neutral: number;
  negative: number;
}

export interface HotComment {
  comment_id: string;
  note_id: string;
  user_id?: string | null;
  content: string | null;
  like_count: number;
  nickname: string | null;
  create_time?: string | null;
  is_top_hot?: 0 | 1;
}

export interface CommentInsights {
  total_comments: number;
  top_keywords: KeywordCount[];
  sentiment: SentimentDistribution;
  top_hot_comments: HotComment[];
}

// ────────────────────────────────────────────────────────────────────────────
// AI 报告 (AIReport)
// ────────────────────────────────────────────────────────────────────────────

export type AIProvider = 'openai' | 'deepseek' | 'gemini';

export interface AIReport {
  id: number;
  task_id: number;
  provider: AIProvider;
  model: string;
  prompt_version: string;
  report_md: string;
  created_at: string;
}

export type AIReportChatRole = 'user' | 'assistant';

export interface AIReportChatMessage {
  role: AIReportChatRole;
  content: string;
}

export interface AIReportChatResponse {
  provider: AIProvider;
  model: string;
  message: string;
}

export interface TopicMetric {
  label: string;
  value: string;
}

export interface TopicRecommendation {
  id: string;
  title: string;
  score: number;
  summary: string;
  metrics: TopicMetric[];
  evidence: string;
  audience: string;
  risk: string;
}

export interface CreativeDirection {
  id: string;
  type: string;
  title: string;
  hook: string;
  promise: string;
  audience: string;
  evidence: string;
}

export interface TitleCandidate {
  text: string;
  reason: string;
}

export interface OutlineBlock {
  title: string;
  points: string[];
}

export interface ContentOutline {
  titles: TitleCandidate[];
  outline: OutlineBlock[];
  cover_copy: string[];
  comment_guide: string[];
  tags: string[];
  evidence: string;
}

export interface ContentDraft {
  title: string;
  cover: string;
  body: string;
  tags: string[];
  checks: string[];
}

// ────────────────────────────────────────────────────────────────────────────
// 通用响应包装
// ────────────────────────────────────────────────────────────────────────────

/** 分页响应(items + total)。 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

/**
 * 后端统一错误响应:`{"code", "message", "detail"}`。
 *
 * 设计文档 §3 规定所有接口在错误时返回该结构。
 */
export interface ApiErrorBody {
  code: number | string;
  message: string;
  detail?: unknown;
}
