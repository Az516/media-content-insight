import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import App from './App';

describe('App router scaffolding', () => {
  it('renders the workspace at `/`', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: '真实采集工作台' })).toBeInTheDocument();
  });

  it('renders the track search page', () => {
    render(
      <MemoryRouter initialEntries={['/track-search']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: '关键词采集' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '当前采集任务' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /抖音/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /公众号/ })).toBeDisabled();
  });

  it('renders all redesigned primary routes', () => {
    const routes = [
      ['/opportunities', '真实内容素材'],
      ['/draft-review', '触达草稿审核'],
      ['/leads', '真实热门评论'],
      ['/reports', '真实报告'],
      ['/integrations', '真实数据连接状态'],
    ];

    routes.forEach(([path, title]) => {
      const { unmount } = render(
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>,
      );
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
      unmount();
    });
  });

  it('redirects unknown routes back to the workspace', () => {
    render(
      <MemoryRouter initialEntries={['/this/does/not/exist']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: '真实采集工作台' })).toBeInTheDocument();
  });
});
