/**
 * 全局 Axios 实例 (`frontend/src/api/client.ts`)。
 *
 * 需求 17.2 规定:Base URL 默认 `http://127.0.0.1:8000/api`,
 * 单次请求超时 30 秒。所有 `frontend/src/api/*.ts` 必须复用此实例。
 */
import axios, { AxiosError, AxiosInstance } from 'axios';

import type { ApiErrorBody } from '@/types/models';

/** 默认后端基础 URL,严格本机访问以满足合规约束(需求 19.11、20.1)。 */
const DEFAULT_BASE_URL = 'http://127.0.0.1:8000/api';

/** 单次请求超时(毫秒),需求 17.2。 */
export const REQUEST_TIMEOUT_MS = 30_000;

/** 通过 Vite 环境变量 `VITE_API_BASE_URL` 覆盖默认 baseURL,便于本机调试。 */
const baseURL: string =
  (import.meta.env?.VITE_API_BASE_URL as string | undefined)?.trim() ||
  DEFAULT_BASE_URL;

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  },
});

/**
 * 把 axios 错误统一抽取为 `ApiErrorBody`,便于上层渲染错误码与消息。
 *
 * 后端在错误时返回 `{"code", "message", "detail"}`(design §3),
 * 网络异常或 axios 自身错误退化为 `code="NETWORK_ERROR"`。
 */
export function extractApiError(err: unknown): ApiErrorBody {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<Partial<ApiErrorBody>>;
    const body = ax.response?.data;
    if (body && (body.code !== undefined || body.message)) {
      return {
        code: body.code ?? ax.response?.status ?? 'UNKNOWN',
        message: body.message ?? ax.message,
        detail: body.detail,
      };
    }
    return {
      code: ax.response?.status ?? 'NETWORK_ERROR',
      message: ax.message,
    };
  }
  return {
    code: 'UNKNOWN',
    message: err instanceof Error ? err.message : String(err),
  };
}

export default apiClient;
