import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import QuestionBanksPage from './QuestionBanksPage';
import { setApp, testApp } from '../test/appContext';
import { makeBank } from '../test/fixtures';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));

const renderPage = () =>
  render(
    <MemoryRouter>
      <QuestionBanksPage />
    </MemoryRouter>,
  );

describe('Question banks list: who sees Edit', () => {
  it.each(['Teacher', 'Admin'] as const)('shows %s an Edit button on each bank (grid and list)', async (role) => {
    setApp(role, { questionBanks: [makeBank()] });
    renderPage();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'List view' }));
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('hides Edit from students in both views, but keeps View and Delete', async () => {
    setApp('Student', { questionBanks: [makeBank()] });
    renderPage();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'List view' }));
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });
});
