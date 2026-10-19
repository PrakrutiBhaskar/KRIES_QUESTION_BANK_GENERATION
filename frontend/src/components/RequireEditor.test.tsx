import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RequireEditor from './RequireEditor';
import { setApp, testApp } from '../test/appContext';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/syllabus']}>
      <Routes>
        <Route path="/syllabus" element={<RequireEditor><p>Seed the syllabus</p></RequireEditor>} />
        <Route path="/dashboard" element={<p>Dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RequireEditor', () => {
  it.each(['Teacher', 'Admin'] as const)('shows the page to a %s', (role) => {
    setApp(role);
    renderGuarded();
    expect(screen.getByText('Seed the syllabus')).toBeInTheDocument();
  });

  it('sends a student to the dashboard', () => {
    setApp('Student');
    renderGuarded();
    expect(screen.queryByText('Seed the syllabus')).not.toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('sends someone who is not signed in to the dashboard', () => {
    setApp(null);
    renderGuarded();
    expect(screen.queryByText('Seed the syllabus')).not.toBeInTheDocument();
  });
});
