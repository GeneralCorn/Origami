"use client";

import { useEffect, useRef } from "react";

const MAX_YAW = 15;
const MAX_PITCH = 10;
// Degrees of fold per unit of travel across the crease, where one unit is the
// full width of the plate. At 260 a drag of a little under two thirds folds the
// sheet completely, and a third of the plate passes the 90 degree mark where
// settle() commits to the fold rather than returning it to flat.
const FOLD_GAIN = 260;
const ARC_FADE = 54;
// Only touch and pen drags compete with the page scroller, and they lose the
// plate once they are steeper than this. The cut is 60 degrees rather than 45
// because the gesture the crease implies is the corner-to-corner drag, which on
// a square plate is exactly 45: a boundary there decides the site's own
// signature gesture by float rounding of the first sampled move.
const FOLD_CONE_TAN = Math.tan((60 * Math.PI) / 180);

// Each completed fold halves the paper, so the plate keeps a quarter turn and a
// factor of root two smaller every time. Four is where it stops: the caption
// leans on the old claim that nothing folds more than seven times, and the
// sheet gives up one fold early rather than labour the joke.
const FIGURES = [
  "fig. 1 · preliminary base",
  "fig. 2 · folded once",
  "fig. 3 · folded twice",
  "fig. 4 · folded three times",
];
const MAX_FOLDS = FIGURES.length;
const STACK_SCALE = Math.SQRT1_2;
// Shards of the burst. Odd count so the spray never reads as a mirrored pair.
const SHARDS = 21;

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
      {/* A preliminary base creases both diagonals and both centre lines. This
          one is grey rather than accent because the accent marks the fold the
          sheet actually performs, which is the main diagonal in Marks. */}
      <line x1="30" y1="170" x2="170" y2="310" stroke="#e7e0d0" strokeWidth="1" strokeDasharray="4 8" />
    </svg>
  );
}

// Marks that belong to the plate rather than to the paper. Unclipped, last in
// DOM order, and never rotated by the flap.
function Marks() {
  return (
    <svg viewBox="0 0 340 340" fill="none" aria-hidden="true" className="fold-marks">
      {/* The rotation axis, and therefore the crease being made. Accent
          coloured because it is the line the sheet actually turns about. */}
      <line x1="30" y1="30" x2="310" y2="310" stroke="#bc3f1d" strokeWidth="1.25" strokeDasharray="6 6" opacity="0.7" />
      {/* The 0.7 stays on each path, exactly as the original artwork had it, so
          the arc rasterises identically at rest. Group opacity would render both
          strokes into one buffer and fade it once, which stops them darkening
          where they overlap at the arrowhead. The group is therefore a plain
          0..1 multiplier that only the fade writes to. */}
      <g data-arc>
        {/* The free corner is the top right one, and it travels to the bottom
            left across the crease. The arc bulges up and left so it reads as
            the sheet lifting over the fold rather than sliding along it. */}
        <path d="M258 82 Q 105 105 82 258" stroke="#bc3f1d" strokeWidth="1.25" opacity="0.7" />
        <path
          d="M82 258 l6.2 -9.1 m-6.2 9.1 l-3.3 -10.5"
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
    const fig = stage.parentElement?.querySelector<HTMLElement>("[data-fig]");
    if (!sheet || !flap || !shade || !cast || !back || !arc) {
      return;
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    let fold = 0;
    let yaw = 0;
    let pitch = 0;
    // Completed folds. Drives how small the paper is and which caption it wears.
    let folds = 0;
    let stackTimer = 0;
    let burstTimer = 0;
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
        stage.classList.remove("is-settling");
        clearHints();
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
        // u is the pointer's signed distance across the crease, which runs
        // along a - b. The fold tracks how far the pointer has travelled from
        // where it grabbed, so the sheet does not teleport to meet a pointer
        // that landed mid-plate.
        //
        // This is displacement rather than absolute position on purpose. Taking
        // acos of the position is geometrically truer, in that it puts the free
        // corner exactly under the pointer, but it makes the sheet almost
        // unfoldable: acos compresses the useful range so hard that dragging
        // clean across the plate turns it only 60 degrees, and settle() returns
        // anything under 90 to flat. Every natural drag therefore snapped back
        // and the sheet read as though it only ever pivoted. Gain is set so a
        // little under two thirds of the plate completes the fold.
        const u = a - b;
        fold = Math.max(0, Math.min(180, grabFold - (u - grabU) * FOLD_GAIN));
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

    // Halving the paper is a layout change, not a rotation, so it is applied to
    // the stage rather than the sheet: the sheet already owns the turn, and two
    // transforms on one element would fight over the same property.
    const applyStack = () => {
      stage.style.setProperty("--stack-scale", Math.pow(STACK_SCALE, folds).toFixed(4));
      stage.style.setProperty("--stack-turn", `${folds * -45}deg`);
      if (fig) {
        fig.textContent = FIGURES[Math.min(folds, MAX_FOLDS - 1)];
      }
    };

    const reset = () => {
      folds = 0;
      fold = 0;
      applyStack();
      schedule();
    };

    // Paper that has run out of folds. Shards inherit the plate's own palette so
    // this reads as the sheet coming apart rather than as a party trick.
    const burst = () => {
      if (reduced.matches) {
        reset();
        return;
      }
      const layer = document.createElement("div");
      layer.className = "fold-burst";
      layer.setAttribute("aria-hidden", "true");
      for (let i = 0; i < SHARDS; i++) {
        const shard = document.createElement("i");
        const angle = (i / SHARDS) * Math.PI * 2 + Math.random() * 0.5;
        const reach = 90 + Math.random() * 130;
        shard.style.setProperty("--dx", `${(Math.cos(angle) * reach).toFixed(1)}px`);
        // Biased downward so the shards fall out of the burst rather than
        // hanging in a ring, which is what makes a radial spray look synthetic.
        shard.style.setProperty("--dy", `${(Math.sin(angle) * reach * 0.7 + 120).toFixed(1)}px`);
        shard.style.setProperty("--spin", `${(Math.random() * 720 - 360).toFixed(0)}deg`);
        shard.style.setProperty("--delay", `${(Math.random() * 90).toFixed(0)}ms`);
        shard.style.setProperty("--edge", i % 5 === 0 ? "#bc3f1d" : "#d9d0bb");
        shard.style.setProperty("--size", `${(7 + Math.random() * 11).toFixed(0)}px`);
        layer.append(shard);
      }
      stage.append(layer);
      stage.classList.add("is-burst");
      burstTimer = window.setTimeout(() => {
        layer.remove();
        stage.classList.remove("is-burst");
        reset();
      }, 1150);
    };

    // A sheet is either flat or creased. There is no stable 47 degrees.
    const settle = () => {
      endGesture();
      stage.classList.add("is-settling");
      const committed = fold > 90;
      fold = committed ? 180 : 0;
      yaw = 0;
      pitch = 0;
      schedule();
      armSettle(reduced.matches ? 20 : 720);
      if (!committed) {
        return;
      }
      // Let the fold finish landing before the paper halves under it, otherwise
      // the shrink cancels the very motion that earned it.
      stackTimer = window.setTimeout(
        () => {
          folds += 1;
          fold = 0;
          if (folds >= MAX_FOLDS) {
            burst();
            return;
          }
          applyStack();
          schedule();
        },
        reduced.matches ? 30 : 640,
      );
    };

    const onDown = (e: PointerEvent) => {
      if (dragging || deciding) {
        return;
      }
      window.clearTimeout(settleTimer);
      measure();
      stage.classList.remove("is-settling");
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
        // A mouse drag never pans the page, so it is free to fold in any
        // direction and needs no lock at all. Only touch and pen have to yield.
        // In practice touch-action: pan-y usually settles that first, at the
        // compositor: a steep swipe arrives here as pointerdown followed
        // straight by pointercancel, with no pointermove in between. This is
        // the backstop for the gestures pan-y does let through.
        deciding = false;
        if (e.pointerType !== "mouse" && Math.abs(dy) > Math.abs(dx) * FOLD_CONE_TAN) {
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
      stage.classList.remove("is-settling");
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

    // A drag left running in a tab that goes away comes back frozen mid-fold,
    // so the tab losing focus ends the gesture at a rest state.
    const onHide = () => {
      if (document.visibilityState === "hidden" && (dragging || deciding)) {
        settle();
      }
    };

    // Deliberately not focusable and carrying no widget role. The plate folds
    // nothing but itself, so a keyboard user gained a tab stop and a
    // "half folded" announcement that told them nothing, and paid for it with
    // arrow, Home and End keys that the handler had to preventDefault, which
    // cost them scrolling and jump-to-top while focus sat on an illustration.
    // Direct manipulation is the whole point of the figure, so it stays a
    // pointer enhancement over artwork that is already complete without it.
    stage.classList.add("is-live");
    if (hint) {
      hint.textContent = " · drag to fold";
    }

    stage.addEventListener("pointerdown", onDown);
    stage.addEventListener("pointermove", onMove);
    stage.addEventListener("pointerenter", onEnter);
    stage.addEventListener("pointerleave", onLeave);
    stage.addEventListener("pointerup", onUp);
    stage.addEventListener("pointercancel", onUp);
    document.addEventListener("visibilitychange", onHide);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      window.clearTimeout(stackTimer);
      window.clearTimeout(burstTimer);
      stage.querySelector(".fold-burst")?.remove();
      stage.removeEventListener("pointerdown", onDown);
      stage.removeEventListener("pointermove", onMove);
      stage.removeEventListener("pointerenter", onEnter);
      stage.removeEventListener("pointerleave", onLeave);
      stage.removeEventListener("pointerup", onUp);
      stage.removeEventListener("pointercancel", onUp);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, []);

  return (
    <div className={className}>
      <div ref={stageRef} className="fold-stage" aria-hidden="true">
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
        <span data-fig>fig. 1 &middot; preliminary base</span>
        <span data-hint aria-hidden="true" />
      </p>
    </div>
  );
}
