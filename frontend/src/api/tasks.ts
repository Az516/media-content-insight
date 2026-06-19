import apiClient from './client';
import type {
  AIReport,
  CommentInsights,
  NoteDetailResponse,
  NoteSummary,
  PaginatedResponse,
  Task,
  TaskListItem,
} from '@/types/models';

export async function createTask(keyword: string, max_notes = 20): Promise<{ task_id: number; status: string }> {
  const { data } = await apiClient.post('/tasks', { keyword, max_notes });
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
  model: string = 'deepseek-chat',
): Promise<{ report_id: number; status: string }> {
  const { data } = await apiClient.post(`/tasks/${taskId}/ai-report`, {
    provider,
    model,
  });
  return data;
}

export async function getAiReport(reportId: number): Promise<AIReport> {
  const { data } = await apiClient.get(`/ai-reports/${reportId}`);
  return data;
}
