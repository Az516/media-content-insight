import apiClient from './client';
import type {
  AIReport,
  AIReportChatMessage,
  AIReportChatResponse,
  CommentInsights,
  ContentDraft,
  ContentOutline,
  CreativeDirection,
  NoteDetailResponse,
  NoteSummary,
  PaginatedResponse,
  Task,
  TaskListItem,
  PlatformKey,
  TopicRecommendation,
} from '@/types/models';

const AI_GENERATION_TIMEOUT_MS = 180_000;

export async function createTask(
  keyword: string,
  max_notes = 20,
  platform: PlatformKey = 'xhs',
): Promise<{ task_id: number; platform: PlatformKey; status: string }> {
  const { data } = await apiClient.post('/tasks', { keyword, max_notes, platform });
  return data;
}

export async function listTasks(): Promise<PaginatedResponse<TaskListItem>> {
  const { data } = await apiClient.get('/tasks');
  return data;
}

export async function getTask(taskId: number): Promise<Task> {
  const { data } = await apiClient.get(`/tasks/${taskId}`);
  return data;
}

export async function listNotes(taskId: number): Promise<PaginatedResponse<NoteSummary>> {
  const { data } = await apiClient.get(`/tasks/${taskId}/notes`);
  return data;
}

export async function getNote(noteId: string): Promise<NoteDetailResponse> {
  const { data } = await apiClient.get(`/notes/${noteId}`);
  return data;
}

export async function getInsights(taskId: number): Promise<CommentInsights> {
  const { data } = await apiClient.get(`/tasks/${taskId}/comments`);
  return data;
}

export async function createAiReport(
  taskId: number,
  provider: 'openai' | 'deepseek' | 'gemini' = 'deepseek',
  model: string = 'gpt-5.5',
): Promise<{ report_id: number; status: string }> {
  const { data } = await apiClient.post(`/tasks/${taskId}/ai-report`, {
    provider,
    model,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function getAiReport(reportId: number): Promise<AIReport> {
  const { data } = await apiClient.get(`/ai-reports/${reportId}`);
  return data;
}

export async function chatWithAiReport(
  reportId: number,
  message: string,
  model = 'gpt-5.5',
  history: AIReportChatMessage[] = [],
): Promise<AIReportChatResponse> {
  const { data } = await apiClient.post(`/ai-reports/${reportId}/chat`, {
    message,
    model,
    history,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function generateTopicRecommendations(
  taskId: number,
  model = 'gpt-5.5',
): Promise<{ items: TopicRecommendation[] }> {
  const { data } = await apiClient.post(`/tasks/${taskId}/content-topics`, {
    provider: 'deepseek',
    model,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function generateCreativeDirections(
  taskId: number,
  opportunity: TopicRecommendation,
  model = 'gpt-5.5',
): Promise<{ items: CreativeDirection[] }> {
  const { data } = await apiClient.post(`/tasks/${taskId}/content-directions`, {
    provider: 'deepseek',
    model,
    opportunity,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function generateContentOutline(
  taskId: number,
  opportunity: TopicRecommendation,
  direction: CreativeDirection,
  model = 'gpt-5.5',
): Promise<ContentOutline> {
  const { data } = await apiClient.post(`/tasks/${taskId}/content-outline`, {
    provider: 'deepseek',
    model,
    opportunity,
    direction,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function generateContentDraft(
  taskId: number,
  opportunity: TopicRecommendation,
  direction: CreativeDirection,
  outline: ContentOutline,
  selectedTitle: string | null,
  model = 'gpt-5.5',
): Promise<ContentDraft> {
  const { data } = await apiClient.post(`/tasks/${taskId}/content-draft`, {
    provider: 'deepseek',
    model,
    opportunity,
    direction,
    outline,
    selected_title: selectedTitle,
  }, {
    timeout: AI_GENERATION_TIMEOUT_MS,
  });
  return data;
}
