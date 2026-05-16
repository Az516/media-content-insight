import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import App from './App';

describe('App router scaffolding (任务 1.5)', () => {
  it('在 `/` 渲染 Home 占位组件', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('placeholder-Home')).toBeInTheDocument();
  });

  it('在 `/tasks/:taskId` 渲染 TaskDetail 并解析路由参数', () => {
    render(
      <MemoryRouter initialEntries={['/tasks/42']}>
        <App />
      </MemoryRouter>,
    );
    const node = screen.getByTestId('placeholder-TaskDetail');
    expect(node).toBeInTheDocument();
    expect(node).toHaveTextContent('42');
  });

  it('在 `/tasks/:taskId/notes/:noteId` 同时解析 taskId / noteId', () => {
    render(
      <MemoryRouter initialEntries={['/tasks/7/notes/abc123']}>
        <App />
      </MemoryRouter>,
    );
    const node = screen.getByTestId('placeholder-NoteDetail');
    expect(node).toHaveTextContent('7');
    expect(node).toHaveTextContent('abc123');
  });

  it('未注册路径走通配 `*` 兜底,渲染 NotFound 占位', () => {
    render(
      <MemoryRouter initialEntries={['/this/does/not/exist']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('placeholder-NotFound')).toBeInTheDocument();
  });
});
