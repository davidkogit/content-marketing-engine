/**
 * Application route configuration.
 *
 * Public routes (no auth required):
 *   /login, /register
 *
 * Protected routes (auth required, wrapped in AppShell layout):
 *   /               — Dashboard (home)
 *   /products       — Product list
 *   /products/:id   — Product detail
 *   /settings       — Super Admin settings (role-gated in sidebar + page)
 *   /categories     — Category management (CRUD)
 *   /segments       — Market segment management (CRUD)
 *   /documents      — Document list with search/filter
 *
 * Layout hierarchy:
 *   <AuthProvider> → <Routes> → <ProtectedRoute> → <AppShell> → pages
 *
 * Uses react-router-dom v6 with lazy-loaded page components for
 * code-splitting.
 */

import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { AppShell } from "@/components/layout/app-shell";

// ── Lazy-Loaded Pages ────────────────────────────────────────────────────────

const DashboardPage = lazy(() => import("@/pages/dashboard-page"));
const ProductsPage = lazy(() => import("@/pages/ProductsPage"));
const ProductDetailPage = lazy(() => import("@/pages/ProductDetailPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const CategoriesPage = lazy(() => import("@/pages/categories-page"));
const SegmentsPage = lazy(() => import("@/pages/segments-page"));
const DocumentsPage = lazy(() => import("@/pages/documents-page"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));
const RegisterPage = lazy(() => import("@/pages/RegisterPage"));

// ── Loading Fallback ─────────────────────────────────────────────────────────

function LoadingFallback() {
  return (
    <div className="flex h-screen w-screen items-center justify-center">
      <div className="text-muted-foreground animate-pulse">Loading…</div>
    </div>
  );
}

// ── App Routes ───────────────────────────────────────────────────────────────

export default function AppRoutes() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* ── Public Routes (no layout) ──────────────────────────────── */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* ── Protected Routes → AppShell Layout → Pages ─────────────── */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="products" element={<ProductsPage />} />
            <Route path="products/:id" element={<ProductDetailPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="categories" element={<CategoriesPage />} />
            <Route path="segments" element={<SegmentsPage />} />
            <Route path="documents" element={<DocumentsPage />} />
          </Route>
        </Route>

        {/* ── Catch-All → Dashboard ──────────────────────────────────── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
