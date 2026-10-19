import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Unmount whatever a test rendered, and start each test from a clean browser state.
afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
});
