import { ThemeProvider } from "@/lib/theme";
import { Router } from "@/lib/router";

import ChatPage from "./pages/chat";
import DatabasePage from "./pages/database";
import DigestPage from "./pages/digest";
import HomePage from "./pages/home";

const ROUTES = [
  { path: "/", element: <HomePage /> },
  { path: "/c/:id", element: <ChatPage /> },
  { path: "/database", element: <DatabasePage /> },
  { path: "/digest", element: <DigestPage /> },
];

export default function App() {
  return (
    <ThemeProvider>
      <Router routes={ROUTES} fallback={<HomePage />} />
    </ThemeProvider>
  );
}
