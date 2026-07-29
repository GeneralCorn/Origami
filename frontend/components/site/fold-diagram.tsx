export function FoldDiagram({ className }: { className?: string }) {
  return (
    <div className={className}>
      <svg viewBox="0 0 340 340" fill="none" aria-hidden="true" className="w-full">
        <rect x="30" y="30" width="280" height="280" fill="#ffffff" stroke="#d9d0bb" strokeWidth="1.25" />
        <line x1="30" y1="30" x2="310" y2="310" stroke="#d9d0bb" strokeWidth="1" strokeDasharray="5 7" />
        <line x1="310" y1="30" x2="30" y2="310" stroke="#d9d0bb" strokeWidth="1" strokeDasharray="5 7" />
        <line x1="170" y1="30" x2="170" y2="310" stroke="#e7e0d0" strokeWidth="1" strokeDasharray="2 8" />
        <line x1="30" y1="170" x2="310" y2="170" stroke="#e7e0d0" strokeWidth="1" strokeDasharray="2 8" />
        <line x1="30" y1="170" x2="170" y2="310" stroke="#bc3f1d" strokeWidth="1.25" strokeDasharray="6 6" opacity="0.7" />
        <path d="M84 132 C 150 70, 230 70, 296 132" stroke="#bc3f1d" strokeWidth="1.25" opacity="0.7" />
        <path d="M296 132 l-10.5 -2 m10.5 2 l-3 -10" stroke="#bc3f1d" strokeWidth="1.25" strokeLinecap="round" opacity="0.7" />
        <circle cx="170" cy="170" r="2.5" fill="#d9d0bb" />
      </svg>
      <p className="mt-3 text-center font-mono text-[11px] tracking-[0.14em] text-subtle">
        fig. 1 &middot; preliminary base
      </p>
    </div>
  );
}
