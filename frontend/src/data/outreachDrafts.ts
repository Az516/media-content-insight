import type { HotComment, TaskListItem } from '@/types/models';

export type OutreachDraftChannel = 'comment' | 'dm';
export type OutreachDraftStatus = 'pending' | 'copied' | 'done';

export interface OutreachDraft {
  id: string;
  task_id: number;
  task_keyword: string;
  platform?: string;
  channel: OutreachDraftChannel;
  status: OutreachDraftStatus;
  source_comment_id: string;
  source_note_id: string;
  source_user_id?: string | null;
  source_nickname?: string | null;
  source_content: string;
  draft_text: string;
  created_at: string;
  updated_at: string;
}

const STORAGE_KEY = 'media-insight:outreach-drafts:v1';

function nowIso(): string {
  return new Date().toISOString();
}

function clipText(value: string, max = 72): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max)}...`;
}

function buildDraftText(task: TaskListItem, comment: HotComment, channel: OutreachDraftChannel): string {
  const keyword = task.keyword || '这个话题';
  const nickname = comment.nickname || '你好';
  const source = clipText(comment.content || '你提到的这个点');

  if (channel === 'comment') {
    return `${nickname}，看到你提到「${source}」，这个反馈很有代表性。我正在整理「${keyword}」相关内容，想听听你最关心的是哪一块？`;
  }

  return `${nickname}，你好。看到你在「${keyword}」相关评论里提到「${source}」，这个点我记下来了。如果你愿意，我可以先把相关资料或案例整理成一版给你参考。`;
}

function parseDrafts(raw: string | null): OutreachDraft[] {
  if (!raw) return [];
  try {
    const value = JSON.parse(raw);
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function listOutreachDrafts(): OutreachDraft[] {
  if (typeof window === 'undefined') return [];
  return parseDrafts(window.localStorage.getItem(STORAGE_KEY)).sort((a, b) =>
    b.updated_at.localeCompare(a.updated_at),
  );
}

export function saveOutreachDrafts(drafts: OutreachDraft[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
}

export function createOutreachDrafts(
  task: TaskListItem,
  comments: HotComment[],
  channels: OutreachDraftChannel[],
): OutreachDraft[] {
  const existing = listOutreachDrafts();
  const byId = new Map(existing.map((draft) => [draft.id, draft]));
  const timestamp = nowIso();

  comments.forEach((comment) => {
    channels.forEach((channel) => {
      const id = `${task.id}:${comment.comment_id}:${channel}`;
      const previous = byId.get(id);
      byId.set(id, {
        id,
        task_id: task.id,
        task_keyword: task.keyword,
        platform: task.platform,
        channel,
        status: previous?.status ?? 'pending',
        source_comment_id: comment.comment_id,
        source_note_id: comment.note_id,
        source_user_id: comment.user_id,
        source_nickname: comment.nickname,
        source_content: comment.content || '',
        draft_text: previous?.draft_text || buildDraftText(task, comment, channel),
        created_at: previous?.created_at ?? timestamp,
        updated_at: timestamp,
      });
    });
  });

  const next = Array.from(byId.values()).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  saveOutreachDrafts(next);
  return next;
}

export function updateOutreachDraft(id: string, changes: Partial<OutreachDraft>): OutreachDraft[] {
  const timestamp = nowIso();
  const next = listOutreachDrafts().map((draft) =>
    draft.id === id ? { ...draft, ...changes, updated_at: timestamp } : draft,
  );
  saveOutreachDrafts(next);
  return next;
}
