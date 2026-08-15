export default function Card({ title, eyebrow, children, className = "" }) {
  return (
    <section className={`border border-line rounded-sm bg-paper ${className}`}>
      {(title || eyebrow) && (
        <header className="px-5 pt-4 pb-3 border-b border-line">
          {eyebrow && (
            <p className="font-body text-[11px] uppercase tracking-widest text-ink-soft mb-0.5">
              {eyebrow}
            </p>
          )}
          {title && <h2 className="font-display text-lg text-ink">{title}</h2>}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
