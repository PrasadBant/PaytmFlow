import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { ReviewShell } from '../components/ReviewShell';
import { ReviewDashboard } from '../screens/review/ReviewDashboard';
import { ReviewQueue } from '../screens/review/ReviewQueue';
import { ReviewCaseDetail } from '../screens/review/ReviewCaseDetail';
import {
  Screen01Home,
  Screen02JourneySelection,
  Screen03GoalBasicInfo,
  Screen04CurrentStatus,
  Screen05Recommendation,
  Screen06UploadEvidence,
  Screen07AiAnalysis,
  Screen08UpdatedStatus,
  Screen09CompleteJourney,
  Screen10MyJourneys,
  HelpScreen,
  NotFoundScreen,
  KitchenSink,
} from '../screens';

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Screen01Home /> },
      { path: 'start', element: <Screen02JourneySelection /> },
      { path: 'start/:type', element: <Screen03GoalBasicInfo /> },
      { path: 'j/:id', element: <Screen04CurrentStatus /> },
      { path: 'j/:id/next', element: <Screen05Recommendation /> },
      { path: 'j/:id/act/:actionId', element: <Screen06UploadEvidence /> },
      { path: 'j/:id/analysis', element: <Screen07AiAnalysis /> },
      { path: 'j/:id/updated', element: <Screen08UpdatedStatus /> },
      { path: 'j/:id/complete', element: <Screen09CompleteJourney /> },
      { path: 'my-journeys', element: <Screen10MyJourneys /> },
      { path: 'help', element: <HelpScreen /> },
      { path: 'dev/kitchen-sink', element: <KitchenSink /> },
      { path: '*', element: <NotFoundScreen /> },
    ],
  },
  {
    path: '/review',
    element: <ReviewShell />,
    children: [
      { index: true, element: <ReviewDashboard /> },
      { path: 'queue', element: <ReviewQueue /> },
      { path: 'case/:caseId', element: <ReviewCaseDetail /> },
    ],
  },
];

export function createAppRouter(): ReturnType<typeof createBrowserRouter> {
  return createBrowserRouter(routes);
}
