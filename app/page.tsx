import Link from 'next/link'

const btnBase =
  'group inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 text-[15px] font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand active:translate-y-px'
const btnPrimary = `${btnBase} bg-brand text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_20px_-8px_rgba(14,90,74,0.7)] hover:bg-brand-deep`
const btnSecondary = `${btnBase} border border-ink/20 bg-surface text-ink hover:border-ink/50`

function Arrow() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-4 w-4 transition-transform duration-150 group-hover:translate-x-0.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  )
}

function Mark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32" className="h-7 w-7">
      <rect width="32" height="32" rx="8" fill="#0e5a4a" />
      <path
        d="M7 22c4-1 5-9 9-9s5 8 9 8"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="16" cy="13" r="2.2" fill="#fff" />
    </svg>
  )
}

const icons = {
  elasticity: (
    <path d="M4 17c3-1 4-10 8-10s5 9 8 10M4 21h16" />
  ),
  forecast: <path d="M3 17l5-5 4 3 8-9M16 6h4v4" />,
  inventory: <path d="M4 8l8-4 8 4-8 4-8-4zM4 8v8l8 4 8-4V8M12 12v8" />,
}

function Icon({ name }: { name: keyof typeof icons }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-6 w-6"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {icons[name]}
    </svg>
  )
}

function DemoCards() {
  return (
    <div className="relative mx-auto w-full max-w-md" aria-label="Example of a directional answer next to a measured answer">
      <p className="mb-3 font-mono text-xs font-medium uppercase tracking-wider text-ink-soft">
        Example &middot; Iced coffee
      </p>

      <div className="rise rounded-2xl border-2 border-dashed border-directional/50 bg-directional-soft p-5" style={{ animationDelay: '250ms' }}>
        <p className="font-mono text-xs font-semibold uppercase tracking-wider text-directional">
          Directional guidance &middot; no data yet
        </p>
        <p className="mt-2 text-[15px] leading-relaxed text-ink">
          Cafes with walk-in competition tend to be price-sensitive on drinks. Test small changes
          before big ones.
        </p>
      </div>

      <div className="rise mt-4 rounded-2xl border border-measured/30 bg-surface p-5 shadow-[0_18px_40px_-24px_rgba(31,79,216,0.45)]" style={{ animationDelay: '450ms' }}>
        <p className="font-mono text-xs font-semibold uppercase tracking-wider text-measured">
          Measured &middot; fitted to your sales
        </p>
        <div className="mt-3 flex items-baseline gap-3">
          <span className="font-mono text-5xl font-semibold tracking-tight text-ink">&minus;1.4</span>
          <span className="text-sm text-ink-soft">price elasticity</span>
        </div>

        <div
          role="img"
          aria-label="Elasticity estimate of minus 1.4 with a 95 percent confidence range from minus 1.7 to minus 1.1"
          className="mt-5"
        >
          <div className="relative h-8">
            <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-line" />
            <div
              className="draw absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-measured/35"
              style={{ left: '20%', width: '40%' }}
            />
            <div className="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 bg-ink/50" style={{ left: '66.7%' }} />
            <div
              className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-measured shadow"
              style={{ left: '40%' }}
            />
          </div>
          <div className="relative mt-1 h-4 font-mono text-[11px] text-ink-soft">
            <span className="absolute left-0">&minus;2.0</span>
            <span className="absolute -translate-x-1/2" style={{ left: '66.7%' }}>
              &minus;1.0
            </span>
            <span className="absolute right-0">&minus;0.5</span>
          </div>
        </div>

        <p className="mt-4 text-[15px] leading-relaxed text-ink">
          A 10% price rise cuts units by about 14%. 95% range: &minus;1.7 to &minus;1.1.
        </p>
        <p className="mt-3 border-t border-line pt-3 text-xs text-ink-soft">
          Illustration only. Your numbers come from your own uploaded data.
        </p>
      </div>
    </div>
  )
}

const unlocks = [
  {
    icon: 'elasticity' as const,
    title: 'Price elasticity',
    body: 'How much your sales move when a price moves, with a confidence range so you know how far to trust it.',
    needs: 'Needs sales history',
  },
  {
    icon: 'forecast' as const,
    title: 'Demand forecast',
    body: 'What each product is likely to sell next, with an interval around the forecast instead of a single guess.',
    needs: 'Needs sales history',
  },
  {
    icon: 'inventory' as const,
    title: 'Inventory signals',
    body: 'Which products risk running out and which are sitting too long, based on stock against how fast they sell.',
    needs: 'Needs stock levels',
  },
]

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-paper text-ink">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand">
          <Mark />
          <span className="font-display text-lg font-semibold tracking-tight">Price Elasticity</span>
        </Link>
        <Link
          href="/login"
          className="inline-flex min-h-11 items-center rounded-xl px-4 text-[15px] font-semibold text-ink transition-colors hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          Sign in
        </Link>
      </header>

      <main className="flex-1">
        <section className="mx-auto grid w-full max-w-6xl items-center gap-12 px-5 pb-20 pt-10 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16 lg:pt-16">
          <div>
            <h1
              className="rise font-display text-[2.6rem] font-semibold leading-[1.02] tracking-tight sm:text-6xl lg:text-[4.25rem]"
              style={{ animationDelay: '60ms' }}
            >
              Know which prices can move, and which can&rsquo;t.
            </h1>
            <p
              className="rise mt-6 max-w-xl text-lg leading-relaxed text-ink-soft"
              style={{ animationDelay: '160ms' }}
            >
              Describe your business and get guidance in minutes. Upload your sales and stock data
              and it becomes measured price elasticity, demand forecasts and inventory signals.
            </p>
            <div
              className="rise mt-9 flex flex-col gap-3 sm:flex-row"
              style={{ animationDelay: '260ms' }}
            >
              <Link href="/login" className={btnPrimary}>
                Describe your business
                <Arrow />
              </Link>
              <a href="#how" className={btnSecondary}>
                How it works
              </a>
            </div>
            <p className="rise mt-5 text-sm text-ink-soft" style={{ animationDelay: '340ms' }}>
              Your data is visible only to your account.
            </p>
          </div>

          <DemoCards />
        </section>

        <section id="how" className="border-y border-line bg-surface">
          <div className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
            <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
              Two kinds of answers, always labelled.
            </h2>
            <div className="mt-10 grid gap-6 md:grid-cols-2">
              <div className="rounded-2xl border-2 border-dashed border-directional/50 bg-directional-soft p-7">
                <p className="font-mono text-xs font-semibold uppercase tracking-wider text-directional">
                  Before you upload anything
                </p>
                <h3 className="mt-3 font-display text-2xl font-semibold tracking-tight">
                  Directional guidance
                </h3>
                <p className="mt-3 leading-relaxed text-ink">
                  Tell us your location, industry, a short description and how you compete. You get
                  AI-written guidance for businesses like yours, marked as guidance and never
                  presented as a measurement.
                </p>
              </div>
              <div className="rounded-2xl border border-measured/30 bg-measured-soft p-7">
                <p className="font-mono text-xs font-semibold uppercase tracking-wider text-measured">
                  After you upload data
                </p>
                <h3 className="mt-3 font-display text-2xl font-semibold tracking-tight">
                  Measured results
                </h3>
                <p className="mt-3 leading-relaxed text-ink">
                  Every number is fitted to your own sales and stock, with a range around it. The AI
                  explains the results, and can only quote numbers that were actually computed.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <h2 className="max-w-2xl font-display text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
            What your data unlocks
          </h2>
          <ul className="mt-10 grid gap-6 md:grid-cols-3">
            {unlocks.map((u) => (
              <li key={u.title} className="rounded-2xl border border-line bg-surface p-7">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10 text-brand">
                  <Icon name={u.icon} />
                </span>
                <h3 className="mt-5 font-display text-xl font-semibold tracking-tight">{u.title}</h3>
                <p className="mt-2 leading-relaxed text-ink-soft">{u.body}</p>
                <p className="mt-4 font-mono text-xs font-medium uppercase tracking-wider text-ink-soft">
                  {u.needs}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section className="mx-auto w-full max-w-6xl px-5 pb-24 sm:px-8">
          <div className="flex flex-col items-start justify-between gap-8 rounded-3xl bg-ink px-8 py-12 text-white sm:px-12 md:flex-row md:items-center">
            <div className="max-w-xl">
              <h2 className="font-display text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                Start with what you already know about your business.
              </h2>
              <p className="mt-3 text-white/75">
                Five short questions, then your first guidance. Add data whenever you&rsquo;re ready.
              </p>
            </div>
            <Link
              href="/login"
              className={`${btnBase} shrink-0 bg-white text-ink hover:bg-white/90 focus-visible:outline-white`}
            >
              Describe your business
              <Arrow />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <p className="mx-auto w-full max-w-6xl px-5 py-6 text-sm text-ink-soft sm:px-8">
          Price Elasticity. Guidance is labelled as guidance; measured numbers come from your data.
        </p>
      </footer>
    </div>
  )
}
