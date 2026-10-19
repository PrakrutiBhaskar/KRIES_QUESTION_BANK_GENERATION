import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from './Sidebar';
import { setApp, testApp } from '../test/appContext';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));

const renderSidebar = () =>
  render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );

describe('Sidebar tabs by role', () => {
  it('shows a teacher the Syllabus tab but not the Figure Library', () => {
    setApp('Teacher');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Syllabus' })).toHaveAttribute('href', '/syllabus');
    expect(screen.queryByRole('link', { name: 'Figure Library' })).not.toBeInTheDocument();
  });

  it('shows an administrator both', () => {
    setApp('Admin');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Syllabus' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Figure Library' })).toBeInTheDocument();
  });

  it('shows a student neither, but keeps the everyday tabs', () => {
    setApp('Student');
    renderSidebar();
    expect(screen.queryByRole('link', { name: 'Syllabus' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Figure Library' })).not.toBeInTheDocument();
    for (const name of ['Dashboard', 'Generate', 'Question Papers', 'Question Banks']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
  });
});
