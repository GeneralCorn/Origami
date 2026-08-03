import { Suspense, lazy } from "react";

import { ThemeProvider } from "@/lib/theme";
import { Router } from "@/lib/router";

import ChatPage from "./pages/chat";
import DatabasePage from "./pages/database";
import DigestPage from "./pages/digest";
import HomePage from "./pages/home";
import LibraryPage from "./pages/library";

// Dev-only CodeMirror 6 spike. The lazy() call has to sit inside the DEV
// branch, not outside it: import.meta.env.DEV is replaced with a literal at
// build time, and only then can Rollup drop the arrow function and with it the
// dynamic import, so no CodeMirror chunk is emitted for a production build.
const SPIKE_ROUTES = import.meta.env.DEV
  ? (() => {
      const SpikeCm6Page = lazy(() => import("./pages/spike-cm6"));
      return [
        {
          path: "/spike/cm6",
          element: (
            <Suspense fallback={<div className="p-4 text-sm">loading spike…</div>}>
              <SpikeCm6Page />
            </Suspense>
          ),
        },
      ];
    })()
  : [];

const ROUTES = [
  { path: "/", element: <HomePage /> },
  { path: "/c/:id", element: <ChatPage /> },
  { path: "/database", element: <DatabasePage /> },
  { path: "/library", element: <LibraryPage /> },
  { path: "/digest", element: <DigestPage /> },
  ...SPIKE_ROUTES,
];

export default function App() {
  return (
    <ThemeProvider>
      <Router routes={ROUTES} fallback={<HomePage />} />
    </ThemeProvider>
  );
}
