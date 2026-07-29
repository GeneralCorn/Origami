import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Minimal hash router.
 *
 * The desktop app has four static routes and one path parameter, and it
 * loads from file:// in packaged builds where history routing does not
 * work. A full routing library brings a large dependency and a steady
 * stream of SSR/RSC advisories that do not apply to a local renderer,
 * so the small amount of matching this needs lives here instead.
 */

interface RouteMatch {
  path: string;
  params: Record<string, string>;
}

const RouterContext = createContext<RouteMatch>({ path: "/", params: {} });

function currentPath(): string {
  const hash = window.location.hash;
  return hash.startsWith("#") ? hash.slice(1) || "/" : "/";
}

export function navigateTo(to: string, options: { replace?: boolean } = {}): void {
  const target = `#${to}`;
  if (options.replace) {
    window.location.replace(target);
  } else {
    window.location.hash = to;
  }
}

export function useNavigate() {
  return useCallback((to: string | number, options: { replace?: boolean } = {}) => {
    if (typeof to === "number") {
      window.history.go(to);
      return;
    }
    navigateTo(to, options);
  }, []);
}

export function useParams<T extends Record<string, string>>(): Partial<T> {
  return useContext(RouterContext).params as Partial<T>;
}

/** Match "/c/:id" against "/c/abc123", returning its params or null. */
function matchRoute(pattern: string, path: string): Record<string, string> | null {
  const patternParts = pattern.split("/").filter(Boolean);
  const pathParts = path.split("/").filter(Boolean);
  if (patternParts.length !== pathParts.length) {
    return null;
  }
  const params: Record<string, string> = {};
  for (let i = 0; i < patternParts.length; i += 1) {
    const patternPart = patternParts[i];
    if (patternPart.startsWith(":")) {
      params[patternPart.slice(1)] = decodeURIComponent(pathParts[i]);
    } else if (patternPart !== pathParts[i]) {
      return null;
    }
  }
  return params;
}

interface RoutesProps {
  routes: Array<{ path: string; element: ReactNode }>;
  fallback: ReactNode;
}

export function Router({ routes, fallback }: RoutesProps) {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const onHashChange = () => setPath(currentPath());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const matched = useMemo(() => {
    for (const route of routes) {
      const params = matchRoute(route.path, path);
      if (params) {
        return { element: route.element, match: { path, params } };
      }
    }
    return { element: fallback, match: { path, params: {} } };
  }, [path, routes, fallback]);

  return (
    <RouterContext.Provider value={matched.match}>
      {matched.element}
    </RouterContext.Provider>
  );
}
