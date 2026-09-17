import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Home from '@/pages/Home'
import AdminLogin from '@/pages/admin/AdminLogin'
import AppointmentsPage from '@/pages/admin/AppointmentsPage'
import CalendarPage from '@/pages/admin/CalendarPage'
import InspectionsPage from '@/pages/admin/InspectionsPage'
import UsersPage from '@/pages/admin/UsersPage'
import AdminShell from '@/components/admin/AdminShell'
import RequireAuth from '@/components/admin/RequireAuth'
import NotFound, { AppErrorBoundary, ErrorPage } from '@/pages/NotFound'
import { AuthProvider } from '@/stores/authContext'

/**
 * App root.
 *
*/
const App: React.FC = () => (
  <AppErrorBoundary>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Customer flow — untouched, and it still sends no token. */}
          <Route path="/" element={<Home />} />

          {/* Admin */}
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route
            path="/admin"
            element={<Navigate to="/admin/appointments" replace />}
          />
          <Route
            path="/admin/appointments"
            element={
              <RequireAuth>
                <AdminShell>
                  <AppointmentsPage />
                </AdminShell>
              </RequireAuth>
            }
          />
          <Route
            path="/admin/calendar"
            element={
              <RequireAuth>
                <AdminShell>
                  <CalendarPage />
                </AdminShell>
              </RequireAuth>
            }
          />
          <Route
            path="/admin/inspections"
            element={
              <RequireAuth>
                <AdminShell>
                  <InspectionsPage />
                </AdminShell>
              </RequireAuth>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RequireAuth minimum="admin">
                <AdminShell>
                  <UsersPage />
                </AdminShell>
              </RequireAuth>
            }
          />

          {/* Explicit error routes, so a link can point at one and so they can
              be opened directly while styling them. */}
          <Route path="/403" element={<ErrorPage code={403} />} />
          <Route path="/500" element={<ErrorPage code={500} />} />

          {/* Catch-all: an unknown path renders the 404 page, NOT a silent
              redirect home — bouncing hides the typo or broken link that
              caused it. */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </AppErrorBoundary>
)

export default App
