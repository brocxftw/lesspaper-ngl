import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShellGuard, AuthGuard, GuestGuard } from "@/features/auth/AuthGuard";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { DocumentsPage } from "@/features/documents/DocumentsPage";
import { LegacyDocumentsRedirect } from "@/features/documents/LegacyDocumentsRedirect";
import { SearchPage } from "@/features/search/SearchPage";
import { AskPage } from "@/features/ask/AskPage";
import { JobsPage } from "@/features/jobs/JobsPage";
import {
  SettingsLayout,
  ProfileSettingsPage,
  UsersSettingsPage,
  AdminSettingsGuard,
} from "@/features/settings/SettingsLayout";
import { ArtificialIntelligencePage } from "@/features/settings/ArtificialIntelligencePage";
import { SystemPage } from "@/features/settings/SystemPage";
import { LogsPage } from "@/features/settings/LogsPage";
import { LibraryPage } from "@/features/settings/LibraryPage";
import { AboutPage } from "@/features/settings/AboutPage";
import { BackupRestorePage } from "@/features/settings/BackupRestorePage";
import { TrashPage } from "@/features/trash/TrashPage";
import { NotFoundPage } from "@/features/not-found/NotFoundPage";
import { SetupPage } from "@/features/auth/SetupPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<GuestGuard />}>
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
          </Route>

          <Route element={<AuthGuard />}>
            <Route element={<AppShellGuard />}>
            <Route path="/" element={<Navigate to="/inbox" replace />} />
            <Route path="/onboarding" element={<Navigate to="/inbox" replace />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route
              path="/documents/folder/:folderId"
              element={<LegacyDocumentsRedirect />}
            />
            <Route
              path="/documents/folder/:folderId/:documentId"
              element={<LegacyDocumentsRedirect />}
            />
            <Route
              path="/documents/:documentId"
              element={<LegacyDocumentsRedirect />}
            />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/ask" element={<AskPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/trash" element={<TrashPage />} />
            <Route path="/settings" element={<SettingsLayout />}>
              <Route index element={<Navigate to="profile" replace />} />
              <Route path="profile" element={<ProfileSettingsPage />} />
              <Route path="profile/users" element={<UsersSettingsPage />} />
              <Route path="artificial-intelligence" element={<AdminSettingsGuard><ArtificialIntelligencePage /></AdminSettingsGuard>} />
              <Route path="library" element={<LibraryPage />} />
              <Route path="backup" element={<AdminSettingsGuard><BackupRestorePage /></AdminSettingsGuard>} />
              <Route path="system" element={<AdminSettingsGuard><SystemPage /></AdminSettingsGuard>} />
              <Route path="logs" element={<AdminSettingsGuard><LogsPage /></AdminSettingsGuard>} />
              <Route path="about" element={<AboutPage />} />
              <Route path="users" element={<Navigate to="/settings/profile/users" replace />} />
              <Route path="storage" element={<Navigate to="/settings/system#storage" replace />} />
              <Route path="ai-providers" element={<Navigate to="/settings/artificial-intelligence?tab=providers" replace />} />
              <Route path="ai-policy" element={<Navigate to="/settings/artificial-intelligence?tab=controls#ai-policy" replace />} />
              <Route path="ai-profiles" element={<Navigate to="/settings/artificial-intelligence?tab=controls" replace />} />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
