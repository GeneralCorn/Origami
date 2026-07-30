"use client";

import { useEffect, useRef } from "react";

const MAX_YAW = 15;
const MAX_PITCH = 10;
const MAX_STEP = 10;
const ARC_FADE = 54;

// The two halves are complementary triangles of the same unmodified artwork.
// The main diagonal, the instruction arc and the centre register dot are NOT in
// here: the arc straddles the crease and would be torn in two by the clips, and
// the diagonal and the dot lie exactly on the rotation axis, so drawing them
// once in an unclipped overlay is both crisper and geometrically exact.
function Plate() {
  return (
    <svg viewBox="0 0 340 340" fill="none" aria-hidden="true" className="w-full">
      <rect x="30" y="30" width="280" height="280" fill="#ffffff" stroke="#d9d0bb" strokeWidth="1.25" />
      <line x1="310" y1="30" x2="30" y2="310" stroke="#d9d0bb" strokeWidth="1" strokeDasharray="5 7" />
      <line x1="170" y1="30" x2="170" y2="310" stroke="#e7e0d0" strokeWidth="1" strokeDasharray="2 8" />
      <line x1="30" y1="170" x2="310" y2="170" stroke="#e7e0d0" strokeWidth="1" strokeDasharray="2 8" />
      <line x1="30" y1="170" x2="170" y2="310" stroke="#bc3f1d" strokeWidth="1.25" strokeDasharray="6 6" opacity="0.7" />
    </svg>
  );
}

// Marks that belong to the plate rather than to the paper. Unclipped, last in
// DOM order, and never rotated by the flap.
function Marks() {
  return (
    <svg viewBox="0 0 340 340" fill="none" aria-hidden="true" className="fold-marks">
      <line x1="30" y1="30" x2="310" y2="310" stroke="#d9d0bb" strokeWidth="1" strokeDasharray="5 7" />
      {/* The 0.7 stays on each path, exactly as the original artwork had it, so
          the arc rasterises identically at rest. Group opacity would render both
          strokes into one buffer and fade it once, which stops them darkening
          where they overlap at the arrowhead. The group is therefore a plain
          0..1 multiplier that only the fade writes to. */}
      <g data-arc>
        <path d="M84 132 C 150 70, 230 70, 296 132" stroke="#bc3f1d" strokeWidth="1.25" opacity="0.7" />
        <path
          d="M296 132 l-10.5 -2 m10.5 2 l-3 -10"
          stroke="#bc3f1d"
          strokeWidth="1.25"
          strokeLinecap="round"
          opacity="0.7"
        />
      </g>
      <circle cx="170" cy="170" r="2.5" fill="#d9d0bb" />
    </svg>
  );
}

export function FoldDiagram({ className }: { className?: string }) {
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }
    const sheet = stage.querySelector<HTMLElement>("[data-sheet]");
    const flap = stage.querySelector<HTMLElement>("[data-flap]");
    const shade = stage.querySelector<HTMLElement>("[data-shade]");
    const cast = stage.querySelector<HTMLElement>("[data-cast]");
    const back = stage.querySelector<HTMLElement>("[data-back]");
    const arc = stage.querySelector<SVGGElement>("[data-arc]");
    const hint = stage.parentElement?.querySelector<HTMLElement>("[data-hint]");
    if (!sheet || !flap || !shade || !cast || !back || !arc) {
      return;
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    let fold = 0;
    let yaw = 0;
    let pitch = 0;
    let grabU = 0;
    let grabFold = 0;
    let pointerId = -1;
    let dragging = false;
    let deciding = false;
    let startX = 0;
    let startY = 0;
    let frame = 0;
    let settleTimer = 0;
    // size starts at 0 rather than 1 so the first pointermove measures. A
    // visitor whose cursor already rests on the plate at load gets no
    // pointerenter, and a placeholder box would map their first move to a
    // rotation of several thousand degrees.
    let box = { left: 0, top: 0, size: 0 };

    const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));
    const label = () => (fold < 45 ? "flat" : fold < 135 ? "half folded" : "folded");

    // Written on release and on keypress only. A live-updating value floods a
    // screen reader during a drag, so it is deliberately absent from paint().
    const announce = () => {
      const value = String(Math.round(fold));
      if (stage.getAttribute("aria-valuenow") === value) {
        return;
      }
      stage.setAttribute("aria-valuenow", value);
      stage.setAttribute("aria-valuetext", label());
    };

    const paint = () => {
      frame = 0;
      sheet.style.transform = `rotateX(${pitch.toFixed(2)}deg) rotateY(${yaw.toFixed(2)}deg)`;
      // Negative, because a positive rotation about (1, 1, 0) drives the flap
      // away from the viewer and it folds behind the sheet instead of over it,
      // disappearing under the fixed half the moment it passes 90 degrees.
      flap.style.transform = `rotate3d(1, 1, 0, ${(-fold).toFixed(2)}deg)`;
      const rad = (fold * Math.PI) / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);
      // Light sits with the reader, so the flap is brightest facing them and
      // darkest edge-on. That is sin, not (1 - cos): a sheet folded flat onto
      // itself is lit exactly like the sheet under it, not dyed grey.
      shade.style.opacity = sin.toFixed(3);
      cast.style.opacity = (sin * 0.62).toFixed(3);
      back.style.opacity = Math.max(0, -cos * 0.72).toFixed(3);
      // The arc is an instruction about the sheet, not a mark on it, so it is
      // spent once the fold is under way. This is a multiplier over the paths'
      // own 0.7, so it runs 1 to 0 rather than 0.7 to 0.
      arc.style.opacity = Math.max(0, 1 - fold / ARC_FADE).toFixed(3);
    };

    const schedule = () => {
      if (!frame) {
        frame = requestAnimationFrame(paint);
      }
    };

    const measure = () => {
      const r = stage.getBoundingClientRect();
      box = { left: r.left, top: r.top, size: r.width || 1 };
    };

    const clearHints = () => {
      sheet.style.willChange = "";
      flap.style.willChange = "";
    };

    // Every path that hands the plate back to CSS goes through here, so a
    // transition class can never outlive its transition. A stale is-settling
    // would put the 620ms settle curve on the hover turn, which is the mush the
    // duration law exists to prevent.
    const armSettle = (duration: number) => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        stage.classList.remove("is-settling", "is-keying");
        clearHints();
        announce();
      }, duration);
    };

    const track = (clientX: number, clientY: number) => {
      const a = (clientX - box.left) / box.size;
      const b = (clientY - box.top) / box.size;
      // Reduced motion keeps the fold, which the visitor asked for with a
      // deliberate gesture, and removes the turn, which follows mere pointer
      // presence and is rotation in depth nobody requested.
      if (reduced.matches) {
        yaw = 0;
        pitch = 0;
      } else {
        // Clamped because pointer capture lets a drag travel well outside the
        // plate, where the raw mapping would swing the turn past its limits.
        yaw = clamp((a - 0.5) * 2 * MAX_YAW, MAX_YAW);
        pitch = clamp((0.5 - b) * 2 * MAX_PITCH, MAX_PITCH);
      }
      if (dragging) {
        // u is the pointer's signed distance from the crease, normalised so the
        // free corner sits at 1. acos(u) is the fold angle that puts that corner
        // under the pointer; taken relative to the grab so the sheet does not
        // teleport to meet a pointer that landed mid-plate.
        const u = Math.max(-1, Math.min(1, a - b));
        const target = grabFold + (Math.acos(u) - Math.acos(grabU)) * (180 / Math.PI);
        // d(theta)/du diverges as |u| approaches 1, so clamp the per-move step.
        const step = clamp(target - fold, MAX_STEP);
        fold = Math.max(0, Math.min(180, fold + step));
      }
      schedule();
    };

    const endGesture = () => {
      if (pointerId !== -1 && stage.hasPointerCapture(pointerId)) {
        stage.releasePointerCapture(pointerId);
      }
      dragging = false;
      deciding = false;
      pointerId = -1;
    };

    // A sheet is either flat or creased. There is no stable 47 degrees.
    const settle = () => {
      endGesture();
      stage.classList.remove("is-keying");
      stage.classList.add("is-settling");
      fold = fold > 90 ? 180 : 0;
      yaw = 0;
      pitch = 0;
      schedule();
      armSettle(reduced.matches ? 20 : 720);
    };

    const onDown = (e: PointerEvent) => {
      if (dragging || deciding) {
        return;
      }
      window.clearTimeout(settleTimer);
      measure();
      stage.classList.remove("is-settling", "is-keying");
      sheet.style.willChange = "transform";
      flap.style.willChange = "transform";
      deciding = true;
      pointerId = e.pointerId;
      startX = e.clientX;
      startY = e.clientY;
    };

    const onMove = (e: PointerEvent) => {
      if (deciding && e.pointerId === pointerId) {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) {
          return;
        }
        // Capture is withheld until the gesture proves itself horizontal. A
        // vertical swipe is never captured, so touch-action: pan-y hands it
        // straight to the page scroller and the page scrolls as normal.
        deciding = false;
        if (Math.abs(dx) <= Math.abs(dy)) {
          pointerId = -1;
          clearHints();
          return;
        }
        dragging = true;
        stage.setPointerCapture(pointerId);
        const a = (e.clientX - box.left) / box.size;
        const b = (e.clientY - box.top) / box.size;
        grabU = Math.max(-1, Math.min(1, a - b));
        grabFold = fold;
      }
      if (!dragging) {
        if (reduced.matches || e.pointerType !== "mouse") {
          return;
        }
        if (!box.size) {
          measure();
        }
      }
      track(e.clientX, e.clientY);
    };

    const onEnter = (e: PointerEvent) => {
      if (dragging || e.pointerType !== "mouse") {
        return;
      }
      window.clearTimeout(settleTimer);
      stage.classList.remove("is-settling", "is-keying");
      measure();
    };

    const onLeave = () => {
      if (dragging || deciding || (yaw === 0 && pitch === 0)) {
        return;
      }
      stage.classList.add("is-settling");
      yaw = 0;
      pitch = 0;
      schedule();
      armSettle(reduced.matches ? 20 : 660);
    };

    const onUp = (e: PointerEvent) => {
      if (e.pointerId !== pointerId) {
        return;
      }
      if (deciding) {
        endGesture();
        clearHints();
        return;
      }
      settle();
    };

    // A keypress is a discrete command, not a manipulation, so it runs on a
    // transition proportional to its travel rather than through the drag path.
    const onKey = (e: KeyboardEvent) => {
      const step = e.shiftKey ? 30 : 10;
      let next = fold;
      let jump = false;
      if (e.key === "ArrowRight" || e.key === "ArrowUp") {
        next = fold + step;
      } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
        next = fold - step;
      } else if (e.key === "Home") {
        next = 0;
        jump = true;
      } else if (e.key === "End") {
        next = 180;
        jump = true;
      } else {
        return;
      }
      e.preventDefault();
      stage.classList.remove("is-settling", "is-keying");
      stage.classList.add(jump ? "is-settling" : "is-keying");
      fold = Math.max(0, Math.min(180, next));
      yaw = 0;
      pitch = 0;
      schedule();
      announce();
      armSettle(jump ? 660 : 260);
    };

    // A drag left running in a tab that goes away comes back frozen mid-fold,
    // so the tab losing focus ends the gesture at a rest state.
    const onHide = () => {
      if (document.visibilityState === "hidden" && (dragging || deciding)) {
        settle();
      }
    };

    stage.classList.add("is-live");
    stage.setAttribute("role", "slider");
    stage.setAttribute("tabindex", "0");
    stage.setAttribute("aria-label", "Fold the paper along its diagonal crease");
    stage.setAttribute("aria-orientation", "horizontal");
    stage.setAttribute("aria-valuemin", "0");
    stage.setAttribute("aria-valuemax", "180");
    announce();
    if (hint) {
      hint.textContent = " · drag to fold";
    }

    stage.addEventListener("pointerdown", onDown);
    stage.addEventListener("pointermove", onMove);
    stage.addEventListener("pointerenter", onEnter);
    stage.addEventListener("pointerleave", onLeave);
    stage.addEventListener("pointerup", onUp);
    stage.addEventListener("pointercancel", onUp);
    stage.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", onHide);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      stage.removeEventListener("pointerdown", onDown);
      stage.removeEventListener("pointermove", onMove);
      stage.removeEventListener("pointerenter", onEnter);
      stage.removeEventListener("pointerleave", onLeave);
      stage.removeEventListener("pointerup", onUp);
      stage.removeEventListener("pointercancel", onUp);
      stage.removeEventListener("keydown", onKey);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, []);

  return (
    <div className={className}>
      <div ref={stageRef} className="fold-stage">
        <div data-sheet className="fold-sheet">
          <div className="fold-half fold-fixed">
            <Plate />
            <div data-cast className="fold-cast" />
          </div>
          <div data-flap className="fold-half fold-flap">
            <Plate />
            <div data-back className="fold-back" />
            <div data-shade className="fold-shade" />
          </div>
          <Marks />
        </div>
      </div>
      <p className="mt-3 text-center font-mono text-[11px] tracking-[0.14em] text-subtle">
        fig. 1 &middot; preliminary base
        <span data-hint />
      </p>
    </div>
  );
}
