import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type Theme = "light" | "dark" | "palenight";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  setTheme: () => {},
});

const STORAGE_KEY = "origami-theme";
const THEMES: Theme[] = ["light", "dark", "palenight"];

/**
 * Resolve a CSS color token to `#rrggbb`.
 *
 * The palette is authored in oklch, which Electron's title bar overlay
 * cannot parse. Reading back `fillStyle` is not enough because Chromium
 * echoes oklch unchanged, so the color is rasterized to a single pixel
 * and read back as bytes. That keeps the conversion tracking the
 * stylesheet rather than duplicating it as a hardcoded table.
 */
function resolveHexColor(cssValue: string): string {
  if (!cssValue) {
    return "";
  }
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return "";
  }
  context.fillStyle = cssValue;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return `#${[r, g, b].map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

/** Repaint the Windows window-control overlay to match the active theme. */
function syncTitleBarTheme() {
  const bridge = window.origami;
  if (!bridge?.setTitleBarTheme) {
    return;
  }
  const styles = getComputedStyle(document.documentElement);
  const color = resolveHexColor(styles.getPropertyValue("--background").trim());
  const symbolColor = resolveHexColor(styles.getPropertyValue("--foreground").trim());
  if (color && symbolColor) {
    bridge.setTitleBarTheme(color, symbolColor);
  }
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  root.classList.remove("dark", "palenight");
  if (t !== "light") root.classList.add(t);
  syncTitleBarTheme();
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");

  // Read persisted theme on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored && THEMES.includes(stored)) {
      setThemeState(stored);
      applyTheme(stored);
    } else {
      syncTitleBarTheme();
    }
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem(STORAGE_KEY, t);
    applyTheme(t);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
