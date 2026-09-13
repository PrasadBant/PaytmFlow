import type { ReactElement } from 'react';
import { RouterProvider } from 'react-router-dom';
import { createAppRouter } from './routes';

export function AppRouter(): ReactElement {
  const router = createAppRouter();
  return <RouterProvider router={router} />;
}
