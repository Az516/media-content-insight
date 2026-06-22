import { Navigate, Route, Routes } from 'react-router-dom';

import AppShell from '@/components/AppShell';
import DraftReview from '@/pages/DraftReview';
import Insights from '@/pages/Insights';
import Integrations from '@/pages/Integrations';
import LeadDetail from '@/pages/LeadDetail';
import NoteDetail from '@/pages/NoteDetail';
import NoteList from '@/pages/NoteList';
import Opportunities from '@/pages/Opportunities';
import Report from '@/pages/Report';
import Reports from '@/pages/Reports';
import TaskDetail from '@/pages/TaskDetail';
import TaskManager from '@/pages/TaskManager';
import TrackSearch from '@/pages/TrackSearch';
import Workspace from '@/pages/Workspace';

export function App(): JSX.Element {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Workspace />} />
        <Route path="track-search" element={<TrackSearch />} />
        <Route path="opportunities" element={<Opportunities />} />
        <Route path="draft-review" element={<DraftReview />} />
        <Route path="leads" element={<LeadDetail />} />
        <Route path="reports" element={<Reports />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="tasks" element={<TaskManager />} />
        <Route path="tasks/:taskId" element={<TaskDetail />} />
        <Route path="tasks/:taskId/notes" element={<NoteList />} />
        <Route path="tasks/:taskId/notes/:noteId" element={<NoteDetail />} />
        <Route path="tasks/:taskId/insights" element={<Insights />} />
        <Route path="tasks/:taskId/report" element={<Report />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Route>
    </Routes>
  );
}

export default App;
