import Link from 'next/link'
import { BackToTop, Nav } from './_landing/chrome'
import { Icon } from './_landing/icons'
import { Reveal } from './_landing/reveal'

const focusRing =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500'

const SCALE_MIN = -2
const SCALE_SPAN = 2
const pct = (v: number) => ((v - SCALE_MIN) / SCALE_SPAN) * 100

function RangeBar({
  point,
  lo,
  hi,
  animate = false,
  label,
}: {
  point: number
  lo: number
  hi: number
  animate?: boolean
  label: string
}) {
  return (
    <div role="img" aria-label={label}>
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-stone-200" />
        <div
          className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-blue-600/30 ${animate ? 'draw' : ''}`}
          style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
        />
        <div className="absolute top-1/2 h-3.5 w-0.5 -translate-y-1/2 bg-stone-400" style={{ left: `${pct(-1)}%` }} />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-blue-600 shadow"
          style={{ left: `${pct(point)}%` }}
        />
      </div>
    </div>
  )
}

function BrowserDashboard() {
  const rows = [
    { name: 'Bread loaf', e: -0.6, lo: -0.8, hi: -0.4, note: 'A price rise should add revenue' },
    { name: 'Iced coffee', e: -1.4, lo: -1.7, hi: -1.1, note: 'A price rise should lose revenue' },
  ]
  return (
    <div
      role="img"
      aria-label="Example dashboard for a corner shop: written guidance, measured elasticity for two products, a four-week forecast and two stock warnings"
      className="rounded-t-2xl border-x border-t border-stone-200 bg-white/50 p-2 shadow-2xl backdrop-blur-xl md:rounded-t-[2rem] md:p-3"
    >
      <div className="relative overflow-hidden rounded-xl border border-stone-100 bg-white shadow-inner">
        <div className="flex items-center gap-2 border-b border-stone-100 bg-stone-50/80 px-4 py-3">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-400/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-400/80" />
          </div>
          <div className="mx-auto hidden whitespace-nowrap rounded border border-stone-200 bg-white px-4 py-1 text-center font-mono text-[10px] text-stone-500 sm:block">
            price-elasticity-predictor.vercel.app/dashboard
          </div>
          <span className="rounded bg-stone-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
            Example data
          </span>
        </div>

        <div className="grid h-[520px] grid-cols-12 md:h-[620px]">
          <aside className="col-span-2 hidden flex-col border-r border-stone-100 bg-stone-50/50 p-4 md:flex">
            <div className="mb-8 flex items-center gap-3 px-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-full border border-white bg-stone-200 text-xs font-bold text-stone-700 shadow-sm">
                AC
              </span>
              <span className="text-xs font-bold text-stone-700">Amara&apos;s Corner Shop</span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2 rounded-md border border-stone-200 bg-white px-2 py-2 font-medium text-stone-800 shadow-sm">
                <Icon name="grid" className="h-3.5 w-3.5 text-orange-700" /> Overview
              </div>
              <div className="flex items-center gap-2 px-2 py-2 text-stone-600">
                <Icon name="sparkle" className="h-3.5 w-3.5" /> Guidance
              </div>
              <div className="flex items-center gap-2 px-2 py-2 text-stone-600">
                <Icon name="curve" className="h-3.5 w-3.5" /> Sales data
              </div>
              <div className="flex items-center gap-2 px-2 py-2 text-stone-600">
                <Icon name="box" className="h-3.5 w-3.5" /> Stock data
              </div>
            </div>
            <p className="mb-2 mt-8 px-2 text-[10px] font-bold uppercase tracking-widest text-stone-500">Products</p>
            <div className="space-y-1 text-xs text-stone-600">
              <div className="flex items-center gap-2 px-2 py-1.5"><span className="h-1.5 w-1.5 rounded-full bg-blue-500" /> Bread loaf</div>
              <div className="flex items-center gap-2 px-2 py-1.5"><span className="h-1.5 w-1.5 rounded-full bg-orange-500" /> Iced coffee</div>
              <div className="flex items-center gap-2 px-2 py-1.5"><span className="h-1.5 w-1.5 rounded-full bg-stone-400" /> Phone credit</div>
            </div>
          </aside>

          <div className="col-span-12 flex h-full flex-col overflow-hidden bg-white bg-[radial-gradient(#e7e5e4_1px,transparent_1px)] [background-size:20px_20px] p-6 md:col-span-10 md:p-8">
            <div className="mb-6">
              <p className="font-serif text-3xl leading-tight text-stone-900 md:text-4xl">Amara&apos;s Corner Shop</p>
              <p className="mt-1 text-sm text-stone-600">Nairobi, Kenya. Grocery. Local competition.</p>
            </div>

            <div className="grid h-full grid-cols-1 gap-5 pb-6 md:grid-cols-3">
              <div className="flex flex-col gap-5 md:col-span-2">
                <div className="rounded-2xl border-2 border-dashed border-stone-300 bg-stone-50 p-5">
                  <p className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-orange-800">
                    <Icon name="sparkle" className="h-3.5 w-3.5" /> Guidance, not measured
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-stone-800">
                    Corner shops with a competitor on the same street tend to lose customers fast on staples
                    like bread, and slowly on convenience items. Try small price changes first.
                  </p>
                </div>

                <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 flex items-center justify-between">
                    <p className="flex items-center gap-2 text-sm font-bold text-stone-800">
                      <Icon name="curve" className="h-4 w-4 text-blue-700" /> Measured from your sales
                    </p>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-stone-500">95% range</span>
                  </div>
                  <div className="space-y-3">
                    {rows.map((r) => (
                      <div key={r.name} className="rounded-xl border border-transparent bg-stone-50 p-3">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-sm font-semibold text-stone-800">{r.name}</span>
                          <span className="font-mono text-sm font-semibold text-stone-900">
                            &minus;{Math.abs(r.e).toFixed(1)}
                            <span className="ml-2 hidden text-[11px] font-normal text-stone-500 sm:inline">
                              ({r.lo.toFixed(1).replace('-', '−')} to {r.hi.toFixed(1).replace('-', '−')})
                            </span>
                          </span>
                        </div>
                        <div className="mt-1">
                          <RangeBar
                            point={r.e}
                            lo={r.lo}
                            hi={r.hi}
                            animate
                            label={`${r.name}: elasticity ${r.e} with a range from ${r.lo} to ${r.hi}`}
                          />
                        </div>
                        <p className="text-[11px] text-stone-600">{r.note}</p>
                      </div>
                    ))}
                    <div className="flex items-center justify-between rounded-xl border border-dashed border-stone-300 p-3">
                      <span className="text-sm font-semibold text-stone-800">Phone credit</span>
                      <span className="text-[11px] text-stone-600">Price never changed, so nothing to fit</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-5">
                <div className="relative flex h-48 flex-col justify-between overflow-hidden rounded-2xl bg-stone-900 p-6 text-white shadow-xl">
                  <div className="absolute -right-12 -top-12 h-32 w-32 rounded-full bg-orange-500/20 blur-2xl" />
                  <div>
                    <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-stone-300">
                      <Icon name="trend" className="h-3.5 w-3.5 text-orange-400" /> Next 4 weeks
                    </p>
                    <p className="mt-3 font-mono text-4xl font-medium tracking-tight">412</p>
                    <p className="text-xs text-stone-300">units of bread, likely range 380 to 445</p>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-stone-700">
                    <div className="ml-[18%] h-full w-[52%] rounded-full bg-orange-400" />
                  </div>
                </div>

                <div className="flex flex-1 flex-col rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                  <p className="mb-4 flex items-center justify-between text-sm font-bold text-stone-800">
                    Stock watch
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-stone-100 text-[10px] text-stone-700">2</span>
                  </p>
                  <div className="space-y-3 text-xs">
                    <div>
                      <p className="font-medium text-stone-800">Bread loaf</p>
                      <p className="mt-1 w-fit rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-bold text-red-800">About 3 days left</p>
                    </div>
                    <div>
                      <p className="font-medium text-stone-800">Phone credit</p>
                      <p className="mt-1 w-fit rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-bold text-stone-700">About 90 days of stock</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="animate-float absolute bottom-10 right-10 z-20 hidden max-w-[15.5rem] items-center gap-3 rounded-xl border border-stone-200 bg-white/95 p-4 shadow-2xl backdrop-blur-xl xl:flex">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-blue-200 bg-blue-50 text-blue-700">
              <Icon name="file" className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-bold text-stone-800">Sales file read</p>
              <p className="text-[11px] leading-snug text-stone-600">1,240 rows used. 1 product skipped because its price never changed.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Home() {
  return (
    <div className="flex flex-1 flex-col overflow-x-hidden bg-[#FAFAF9] text-stone-900">
      <Nav />

      <main>
        <section className="relative isolate flex flex-col justify-center overflow-hidden bg-stone-50 px-6 pb-12 pt-32 lg:pt-44">
          <div className="animate-float pointer-events-none absolute left-1/2 top-0 -z-10 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-orange-200/25 blur-[120px]" />

          <div className="relative z-10 mx-auto max-w-4xl text-center">
            <div className="rise mb-8 inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-4 py-2 shadow-sm" style={{ animationDelay: '40ms' }}>
              <span className="relative flex h-2 w-2" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-600" />
              </span>
              <span className="text-sm font-medium text-stone-700">Guidance today. Measurements once you add data.</span>
            </div>

            <h1 className="rise mb-8 font-serif text-6xl leading-[0.95] text-stone-900 md:text-8xl md:leading-[1.05]" style={{ animationDelay: '120ms' }}>
              Know which prices <span className="italic text-stone-500">can</span> move, and which can&apos;t.
            </h1>

            <p className="rise mx-auto mb-10 max-w-2xl text-lg leading-relaxed text-stone-600 md:text-xl" style={{ animationDelay: '220ms' }}>
              Tell us about your business and you get written guidance right away. Add your sales and stock
              files when you&apos;re ready, and you get measured price elasticity, demand forecasts and
              stock warnings.
            </p>

            <div className="rise flex flex-col items-center justify-center gap-4 sm:flex-row" style={{ animationDelay: '320ms' }}>
              <Link
                href="/login"
                className={`group flex min-h-14 items-center gap-2 rounded-full bg-stone-900 px-8 text-base font-medium text-white shadow-lg transition duration-300 hover:-translate-y-1 hover:bg-stone-800 hover:shadow-xl ${focusRing}`}
              >
                Describe your business
                <Icon name="arrow-right" className="h-4 w-4 transition-transform group-hover:translate-x-1" strokeWidth={2.2} />
              </Link>
              <a
                href="#measure"
                className={`flex min-h-14 items-center gap-2 rounded-full border border-stone-300 bg-white px-8 text-base font-medium text-stone-800 transition hover:border-stone-500 hover:bg-stone-50 ${focusRing}`}
              >
                <Icon name="curve" className="h-4 w-4 text-stone-500" />
                See what you get
              </a>
            </div>
            <p className="rise mt-6 text-sm text-stone-600" style={{ animationDelay: '400ms' }}>
              Guidance is labelled as guidance. Measured numbers only come from your own files.
            </p>
          </div>

          <div className="rise relative mx-auto mt-16 w-full max-w-6xl md:mt-24" style={{ animationDelay: '480ms' }}>
            <BrowserDashboard />
          </div>
        </section>

        <section id="describe" className="overflow-hidden px-6 py-24">
          <Reveal className="mx-auto max-w-7xl rounded-3xl border border-stone-200 bg-white p-8 shadow-xl md:p-16">
            <div className="grid grid-cols-1 items-center gap-16 md:grid-cols-2">
              <div className="group relative">
                <div className="absolute left-4 top-4 -z-10 h-full w-full rotate-3 rounded-2xl bg-stone-100 transition group-hover:rotate-6" />
                <div
                  role="img"
                  aria-label="Example business profile with location, industry, competition and a 16-word description"
                  className="relative -rotate-1 overflow-hidden rounded-2xl border border-stone-100 bg-white p-6 shadow-xl transition duration-500 group-hover:rotate-0 sm:h-[500px] sm:p-8"
                >
                  <p className="mb-6 text-xs text-stone-500">Your profile</p>
                  <p className="mb-6 font-serif text-3xl text-stone-900">Amara&apos;s Corner Shop</p>
                  <dl className="space-y-3 text-sm">
                    <div className="flex justify-between gap-4 border-b border-stone-100 pb-2">
                      <dt className="text-stone-500">Location</dt>
                      <dd className="text-stone-800">Nairobi, Kenya</dd>
                    </div>
                    <div className="flex justify-between gap-4 border-b border-stone-100 pb-2">
                      <dt className="text-stone-500">Industry</dt>
                      <dd className="text-stone-800">Grocery and convenience</dd>
                    </div>
                    <div className="flex justify-between gap-4 border-b border-stone-100 pb-2">
                      <dt className="text-stone-500">Competition</dt>
                      <dd className="text-stone-800">Local, within walking distance</dd>
                    </div>
                  </dl>
                  <div className="mt-4 border-l-2 border-stone-300 pl-4 text-sm italic text-stone-600">
                    &quot;Family shop selling bread, drinks and airtime. Most customers live within five minutes.&quot;
                  </div>
                  <p className="mt-2 text-right font-mono text-[11px] text-stone-500">16 / 25 words</p>

                  <div className="animate-float mt-6 rounded-lg border border-stone-200 bg-white/90 p-2 shadow-2xl backdrop-blur sm:absolute sm:bottom-6 sm:left-8 sm:right-8 sm:mt-0">
                    <div className="flex items-center gap-3 rounded p-2 hover:bg-stone-100">
                      <span className="flex h-6 w-6 items-center justify-center rounded bg-orange-100 text-orange-800">
                        <Icon name="sparkle" className="h-3.5 w-3.5" />
                      </span>
                      <span className="text-sm font-medium">Write my first guidance</span>
                    </div>
                    <div className="flex items-center gap-3 rounded p-2 hover:bg-stone-100">
                      <span className="flex h-6 w-6 items-center justify-center rounded bg-blue-100 text-blue-800">
                        <Icon name="file" className="h-3.5 w-3.5" />
                      </span>
                      <span className="text-sm font-medium">Upload a sales file</span>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <span className="mb-2 block text-xs font-bold uppercase tracking-widest text-orange-800">Describe</span>
                <h2 className="mb-6 font-serif text-5xl leading-tight text-stone-900">Five questions, then a first read</h2>
                <p className="mb-8 text-lg leading-relaxed text-stone-600">
                  Give us your business name, where you are, what you sell and a description in 25 words or
                  fewer. Add how you sell and who you compete with. That&apos;s enough for a first round of
                  written guidance, with no files needed.
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-6">
                  <div className="flex items-start gap-3">
                    <Icon name="store" className="mt-1 h-5 w-5 text-stone-500" />
                    <div>
                      <h4 className="text-sm font-bold">Your industry</h4>
                      <p className="text-xs text-stone-600">Picked from a list, so the questions fit.</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <Icon name="layers" className="mt-1 h-5 w-5 text-stone-500" />
                    <div>
                      <h4 className="text-sm font-bold">Competition</h4>
                      <p className="text-xs text-stone-600">Local, regional, national or online.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </section>

        <section id="measure" className="bg-stone-50 px-6 py-24">
          <Reveal className="relative mx-auto max-w-7xl">
            <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12">
              <div className="flex flex-col justify-center lg:col-span-4">
                <span className="mb-2 block text-xs font-bold uppercase tracking-widest text-orange-800">Measure</span>
                <h2 className="mb-4 font-serif text-5xl leading-tight text-stone-900">
                  Numbers you
                  <br />
                  can check
                </h2>
                <p className="mb-8 leading-relaxed text-stone-600">
                  Upload a sales file and each product gets an elasticity with a range around it. The same file
                  feeds a forecast. Add a stock file and you also see which items are about to run out and
                  which are sitting too long.
                </p>
                <a
                  href="#trust"
                  className={`group inline-flex min-h-11 w-fit items-center gap-2 font-bold text-stone-900 transition hover:text-orange-700 ${focusRing}`}
                >
                  <span className="border-b-2 border-stone-900 pb-0.5 group-hover:border-orange-700">How numbers are labelled</span>
                  <Icon name="arrow-right" className="h-4 w-4" strokeWidth={2.2} />
                </a>
              </div>

              <div className="grid grid-cols-2 gap-4 lg:col-span-8">
                <div className="relative col-span-2 overflow-hidden rounded-3xl border border-stone-200 bg-white p-6 shadow-sm transition duration-300 hover:shadow-lg md:col-span-1">
                  <div className="absolute left-0 top-0 h-1 w-full bg-gradient-to-r from-blue-600 to-blue-300" />
                  <div className="mb-5 flex items-center justify-between">
                    <h3 className="text-lg font-bold">Price elasticity</h3>
                    <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-800">Measured</span>
                  </div>
                  <p className="font-mono text-5xl font-semibold tracking-tight text-stone-900">&minus;1.4</p>
                  <p className="mb-4 mt-1 text-sm text-stone-600">Iced coffee, 95% range &minus;1.7 to &minus;1.1</p>
                  <RangeBar point={-1.4} lo={-1.7} hi={-1.1} label="Elasticity of minus 1.4 with a range from minus 1.7 to minus 1.1" />
                  <div className="relative mt-1 h-4 font-mono text-[11px] text-stone-500">
                    <span className="absolute left-0">&minus;2.0</span>
                    <span className="absolute -translate-x-1/2" style={{ left: `${pct(-1)}%` }}>&minus;1.0</span>
                    <span className="absolute right-0">0</span>
                  </div>
                  <p className="mt-4 text-sm leading-relaxed text-stone-700">A 10% price rise cuts units sold by about 14%.</p>
                </div>

                <div className="col-span-2 flex flex-col rounded-3xl border border-stone-200 bg-white p-6 shadow-sm transition duration-300 hover:shadow-lg md:col-span-1">
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-lg font-bold">Demand forecast</h3>
                    <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-800">Measured</span>
                  </div>
                  <div className="flex-1">
                    <svg
                      viewBox="0 0 220 100"
                      className="h-36 w-full"
                      role="img"
                      aria-label="Eight weeks of past sales as a solid line, then a four-week forecast as a dashed line inside a shaded range that widens over time"
                    >
                      <path d="M140 45 L160 34 L180 28 L200 28 L220 21 L220 57 L200 58 L180 52 L160 50 Z" className="fill-orange-200/70" />
                      <line x1="140" y1="6" x2="140" y2="90" className="stroke-stone-300" strokeDasharray="3 3" />
                      <polyline
                        points="0,60 20,54 40,62 60,50 80,56 100,48 120,52 140,45"
                        fill="none"
                        className="stroke-stone-800"
                        strokeWidth="2.2"
                        strokeLinejoin="round"
                        strokeLinecap="round"
                      />
                      <polyline
                        points="140,45 160,42 180,40 200,43 220,39"
                        fill="none"
                        className="stroke-orange-700"
                        strokeWidth="2.2"
                        strokeDasharray="5 4"
                        strokeLinejoin="round"
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="mt-1 flex justify-between font-mono text-[10px] text-stone-500">
                      <span>Last 8 weeks</span>
                      <span>Next 4</span>
                    </div>
                  </div>
                  <p className="mt-4 text-sm leading-relaxed text-stone-700">
                    The solid line is what sold. The dashed line is the forecast, and the shaded band is the range it
                    should land in.
                  </p>
                </div>

                <div className="col-span-2 flex flex-col items-start justify-between gap-4 rounded-3xl bg-stone-900 p-6 text-white shadow-lg sm:flex-row sm:items-center">
                  <div className="flex items-center gap-4">
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-4 border-orange-500 font-mono text-lg font-bold">2</span>
                    <div>
                      <h3 className="font-bold">Products need a look</h3>
                      <p className="text-xs text-stone-300">One is about to run out. One has months of stock.</p>
                    </div>
                  </div>
                  <Link
                    href="/login"
                    className={`flex min-h-11 items-center rounded-full bg-white px-5 text-xs font-bold text-stone-900 transition hover:bg-stone-200 ${focusRing}`}
                  >
                    Add a stock file
                  </Link>
                </div>
              </div>
            </div>
          </Reveal>
        </section>

        <section id="trust" className="px-6 py-24">
          <div className="mx-auto mb-16 max-w-5xl text-center">
            <span className="mb-2 block text-xs font-bold uppercase tracking-widest text-stone-600">Privacy and labels</span>
            <h2 className="font-serif text-5xl text-stone-900">How we keep the numbers honest</h2>
          </div>

          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 md:grid-cols-3">
            {[
              {
                icon: 'sparkle' as const,
                title: 'Guidance says so',
                body: 'Written advice from your profile is marked as guidance. It never shows up looking like a measurement.',
                accent: 'hover:border-orange-200',
                demo: (
                  <div className="mt-auto rounded-xl border-2 border-dashed border-stone-300 bg-stone-50 p-3">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-orange-800">Guidance, not measured</p>
                    <p className="mt-1 text-xs text-stone-700">Staples tend to be price-sensitive near a competitor.</p>
                  </div>
                ),
              },
              {
                icon: 'curve' as const,
                title: 'Numbers show their range',
                body: 'Every fitted number comes with the range it could fall in. A wide range means the data is thin.',
                accent: 'hover:border-blue-200',
                demo: (
                  <div className="mt-auto rounded-xl border border-stone-100 bg-white p-3 shadow-sm">
                    <p className="mb-1 font-mono text-sm font-semibold">&minus;0.6</p>
                    <RangeBar point={-0.6} lo={-0.8} hi={-0.4} label="Elasticity minus 0.6, range minus 0.8 to minus 0.4" />
                  </div>
                ),
              },
              {
                icon: 'lock' as const,
                title: 'Your data stays yours',
                body: 'Each business can only read its own rows. That rule is set in the database itself.',
                accent: 'hover:border-stone-300',
                demo: (
                  <div className="mt-auto space-y-2 rounded-xl border border-stone-100 bg-white p-2 shadow-sm">
                    <div className="flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50 p-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded bg-stone-900 text-white">
                        <Icon name="store" className="h-4 w-4" />
                      </span>
                      <div className="text-xs font-bold text-stone-800">Your business</div>
                    </div>
                    <div className="flex items-center gap-3 rounded-lg p-2 opacity-60">
                      <span className="flex h-8 w-8 items-center justify-center rounded bg-stone-200 text-stone-600">
                        <Icon name="lock" className="h-4 w-4" />
                      </span>
                      <div className="text-xs font-bold text-stone-800">Other businesses</div>
                    </div>
                  </div>
                ),
              },
            ].map((c, i) => (
              <Reveal key={c.title} delay={i * 100}>
                <div className={`group h-full rounded-3xl border border-stone-200 bg-white p-1 transition duration-500 hover:-translate-y-2 hover:shadow-xl ${c.accent}`}>
                  <div className="flex h-full flex-col rounded-[20px] bg-stone-50 p-8">
                    <span className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-white text-orange-700 shadow-sm transition group-hover:scale-110">
                      <Icon name={c.icon} className="h-6 w-6" />
                    </span>
                    <h3 className="mb-2 text-xl font-bold text-stone-900">{c.title}</h3>
                    <p className="mb-8 text-sm leading-relaxed text-stone-600">{c.body}</p>
                    {c.demo}
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        <section className="px-6 py-20">
          <Reveal className="relative mx-auto max-w-7xl overflow-hidden rounded-[3rem] bg-stone-900 px-6 py-24 text-center">
            <div className="pointer-events-none absolute left-1/2 top-[-100px] h-[400px] w-[600px] -translate-x-1/2 rounded-full bg-orange-600/30 blur-[100px]" />
            <div className="relative z-10">
              <h2 className="mb-6 font-serif text-5xl italic text-white md:text-6xl">Start with what you already know.</h2>
              <p className="mx-auto mb-10 max-w-2xl text-xl text-stone-300">
                Five questions today. A sales file whenever you have one.
              </p>
              <div className="flex flex-col justify-center gap-4 sm:flex-row">
                <Link
                  href="/login"
                  className="group flex min-h-14 items-center justify-center gap-2 rounded-full bg-white px-8 font-bold text-stone-900 shadow-lg transition hover:scale-105 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                >
                  Describe your business
                  <Icon name="arrow-right" className="h-4 w-4 transition-transform group-hover:translate-x-1" strokeWidth={2.2} />
                </Link>
                <Link
                  href="/login"
                  className="flex min-h-14 items-center justify-center rounded-full border border-stone-600 px-8 font-medium text-white transition hover:bg-stone-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                >
                  Sign in
                </Link>
              </div>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-stone-100 bg-white py-16 text-sm text-stone-600">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-10 px-6 md:grid-cols-4">
          <div className="col-span-2">
            <div className="mb-4 flex items-center gap-2 text-stone-900">
              <span className="flex h-6 w-6 items-center justify-center rounded bg-stone-900 font-serif text-sm text-white">P</span>
              <span className="text-lg font-bold tracking-tight">Price Elasticity</span>
            </div>
            <p className="max-w-sm text-stone-600">
              Guidance is labelled as guidance. Measured numbers come from your own data.
            </p>
          </div>
          <div className="flex flex-col">
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-900">Product</p>
            <a href="#describe" className="inline-flex min-h-11 w-fit items-center hover:text-orange-700">Describe</a>
            <a href="#measure" className="inline-flex min-h-11 w-fit items-center hover:text-orange-700">Measure</a>
            <a href="#trust" className="inline-flex min-h-11 w-fit items-center hover:text-orange-700">Privacy and labels</a>
          </div>
          <div className="flex flex-col">
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-stone-900">Account</p>
            <Link href="/login" className="inline-flex min-h-11 w-fit items-center hover:text-orange-700">Sign in</Link>
            <Link href="/login" className="inline-flex min-h-11 w-fit items-center hover:text-orange-700">Get started</Link>
          </div>
        </div>
        <div className="mx-auto mt-14 max-w-7xl border-t border-stone-100 px-6 pt-8">
          <p>&copy; 2026 Price Elasticity</p>
        </div>
      </footer>

      <BackToTop />
    </div>
  )
}
