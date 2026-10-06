'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { BrandLink, focusRing } from '@/app/_ui/brand'
import { Icon, type IconName } from '@/app/_ui/icons'
import { modelLabel } from '@/lib/ai/labels'
import { locationLabel, type Business, type Insight } from '@/lib/business'
import { SCOPE_LABEL, choiceLabel, industryLabel, type ChoiceField } from '@/lib/industries'
import { supabase } from '@/lib/supabase'

type PageState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; business: Business; email: string }

export default function DashboardPage() {
  const router = useRouter()
  const [state, setState] = useState<PageState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data } = await supabase.auth.getSession()
      const session = data.session
      if (!session) {
        router.replace('/login')
        return
      }
      const { data: businesses, error } = await supabase
        .from('businesses')
        .select('*')
        .order('created_at', { ascending: true })
        .limit(1)
      if (cancelled) return
      if (error) {
        setState({ status: 'error', message: error.message })
        return
      }
      if (!businesses || businesses.length === 0) {
        router.replace('/onboarding')
        return
      }
      setState({ status: 'ready', business: businesses[0] as Business, email: session.user.email ?? '' })
    })()
    return () => {
      cancelled = true
    }
  }, [router])

  async function signOut() {
    await supabase.auth.signOut()
    router.replace('/login')
  }

  if (state.status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50">
        <p aria-live="polite" className="font-serif text-2xl text-stone-700">
          Loading your dashboard
        </p>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50 px-6">
        <div className="max-w-md text-center">
          <h1 className="font-serif text-3xl">Your dashboard did not load</h1>
          <p role="alert" className="mt-3 text-stone-600">
            {state.message}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className={`mt-6 min-h-12 rounded-full bg-stone-900 px-6 font-semibold text-white ${focusRing}`}
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  const { business, email } = state
  const k = business.key_components ?? {}
  const details: [ChoiceField, string | null | undefined][] = [
    ['price_point', k.price_point],
    ['channel', k.channel],
    ['customer_type', k.customer_type],
    ['seasonality', k.seasonality],
    ['sku_count', k.sku_count],
  ]
  const chips = details
    .map(([field, value]) => choiceLabel(field, value))
    .filter((label): label is string => Boolean(label))
  if (k.seasonality === 'seasonal' && k.peak_months?.length) chips.push(`Busiest: ${k.peak_months.map((m) => m.slice(0, 3)).join(', ')}`)

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="sticky top-0 z-30 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-2 sm:px-8">
          <BrandLink />
          <div className="flex items-center gap-2">
            <span className="hidden truncate text-sm text-stone-600 sm:inline">{email}</span>
            <button
              type="button"
              onClick={signOut}
              className={`min-h-11 rounded-full px-4 text-sm font-semibold text-stone-700 hover:bg-stone-100 ${focusRing}`}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-20 pt-10 sm:px-8">
        <section aria-labelledby="business-name" className="mb-10">
          <p className="text-xs font-bold uppercase tracking-widest text-orange-800">Your business</p>
          <h1 id="business-name" className="mt-2 font-serif text-5xl leading-tight sm:text-6xl">
            {business.name}
          </h1>
          <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-stone-600">
            <span className="inline-flex items-center gap-1.5">
              <Icon name="pin" className="h-4 w-4" />
              {locationLabel(business)}
            </span>
            <span aria-hidden="true">·</span>
            <span>{industryLabel(business.industry)}</span>
            <span aria-hidden="true">·</span>
            <span>{SCOPE_LABEL[business.competition_scope]}</span>
          </p>
          <blockquote className="mt-5 max-w-2xl border-l-2 border-stone-300 pl-4 font-serif text-xl italic leading-snug text-stone-700">
            &quot;{business.description}&quot;
          </blockquote>
          {chips.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-2" aria-label="Business details">
              {chips.map((chip) => (
                <li key={chip} className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-sm text-stone-700">
                  {chip}
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <InitialGuidance business={business} />
          </div>
          <aside aria-labelledby="add-data-heading" className="space-y-4">
            <h2 id="add-data-heading" className="font-serif text-3xl">
              Add your data
            </h2>
            <UploadCard
              icon="curve"
              title="Sales history"
              body="A file with product, date, price and units sold. Each product then gets a measured price elasticity and a demand forecast."
            />
            <UploadCard
              icon="box"
              title="Stock levels"
              body="Product, date and units on hand. This adds warnings for items about to run out or sitting too long."
            />
          </aside>
        </div>

        <MeasuredNumbers />
      </main>
    </div>
  )
}

type GuidanceState =
  | { status: 'loading' }
  | { status: 'ready'; insight: Insight }
  | { status: 'error'; message: string }

function InitialGuidance({ business }: { business: Business }) {
  const [state, setState] = useState<GuidanceState>({ status: 'loading' })
  const [rewriting, setRewriting] = useState(false)

  const request = useCallback(
    async (force: boolean): Promise<Insight> => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) throw new Error('Your session ended. Sign in again.')
      const res = await fetch('/api/insights/initial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${data.session.access_token}` },
        body: JSON.stringify({ businessId: business.id, force }),
      })
      const json = (await res.json().catch(() => ({}))) as { insight?: Insight; error?: string }
      if (!res.ok || !json.insight) throw new Error(json.error ?? 'Could not write guidance right now.')
      return json.insight
    },
    [business.id],
  )

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data } = await supabase
        .from('ai_insights')
        .select('*')
        .eq('business_id', business.id)
        .eq('scope', 'initial')
        .order('created_at', { ascending: false })
        .limit(1)
      const stored = data?.[0] as Insight | undefined
      if (stored && new Date(stored.created_at) >= new Date(business.updated_at)) {
        if (!cancelled) setState({ status: 'ready', insight: stored })
        return
      }
      try {
        const insight = await request(false)
        if (!cancelled) setState({ status: 'ready', insight })
      } catch (err) {
        if (!cancelled) setState({ status: 'error', message: (err as Error).message })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [business.id, business.updated_at, request])

  async function rewrite() {
    setRewriting(true)
    try {
      const insight = await request(true)
      setState({ status: 'ready', insight })
    } catch (err) {
      setState({ status: 'error', message: (err as Error).message })
    } finally {
      setRewriting(false)
    }
  }

  const points = state.status === 'ready' ? state.insight.body.split('\n').filter(Boolean) : []
  const fromModel = state.status === 'ready' && state.insight.grounding?.source === 'model'

  return (
    <section
      aria-labelledby="guidance-heading"
      aria-busy={state.status === 'loading' || rewriting}
      className="h-full rounded-3xl border-2 border-dashed border-stone-300 bg-white p-6 sm:p-8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="inline-flex items-center gap-2 rounded-full bg-orange-50 px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-orange-800">
          <Icon name="sparkle" className="h-3.5 w-3.5" />
          Guidance, not measured
        </p>
        {state.status === 'ready' && (
          <button
            type="button"
            onClick={rewrite}
            disabled={rewriting}
            className={`inline-flex min-h-11 items-center gap-2 rounded-full border border-stone-300 px-4 text-sm font-semibold text-stone-700 transition hover:border-stone-500 disabled:opacity-60 ${focusRing}`}
          >
            <Icon name="refresh" className="h-4 w-4" />
            {rewriting ? 'Writing' : 'Write it again'}
          </button>
        )}
      </div>

      <h2 id="guidance-heading" className="mt-5 font-serif text-3xl sm:text-4xl">
        A first read on your pricing
      </h2>

      {state.status === 'loading' && (
        <div className="mt-6 space-y-4" aria-live="polite">
          <p className="text-sm text-stone-600">Writing guidance from your profile</p>
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2">
              <div className="h-3 w-full animate-pulse rounded bg-stone-100" />
              <div className="h-3 w-4/5 animate-pulse rounded bg-stone-100" />
            </div>
          ))}
        </div>
      )}

      {state.status === 'error' && (
        <div className="mt-6">
          <p role="alert" className="text-stone-700">
            {state.message}
          </p>
          <button
            type="button"
            onClick={rewrite}
            className={`mt-4 min-h-11 rounded-full bg-stone-900 px-5 text-sm font-semibold text-white ${focusRing}`}
          >
            Try again
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <>
          <ul className="mt-6 space-y-4">
            {points.map((point, i) => (
              <li key={i} className="flex gap-3 leading-relaxed text-stone-800">
                <span aria-hidden="true" className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-700" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 border-t border-stone-100 pt-4 text-sm text-stone-600">
            {fromModel
              ? `Written by ${modelLabel(state.insight.model)} using only your profile.`
              : 'Written from general rules for businesses like yours, using your profile.'}{' '}
            Nothing here comes from your sales yet.
          </p>
        </>
      )}
    </section>
  )
}

function UploadCard({ icon, title, body }: { icon: IconName; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-6">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-700">
          <Icon name={icon} className="h-5 w-5" />
        </span>
        <h3 className="text-lg font-bold">{title}</h3>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-stone-600">{body}</p>
      <p className="mt-4 inline-flex items-center gap-2 rounded-full border border-dashed border-stone-300 px-3 py-1.5 text-xs font-semibold text-stone-600">
        <Icon name="upload" className="h-3.5 w-3.5" />
        Upload opens soon
      </p>
    </div>
  )
}

function MeasuredNumbers() {
  const tiles: { icon: IconName; title: string; needs: string }[] = [
    { icon: 'curve', title: 'Price elasticity', needs: 'Needs sales history' },
    { icon: 'trend', title: 'Demand forecast', needs: 'Needs sales history' },
    { icon: 'box', title: 'Stock warnings', needs: 'Needs stock levels' },
  ]
  return (
    <section aria-labelledby="measured-heading" className="mt-6 rounded-3xl border border-stone-200 bg-white p-6 sm:p-8">
      <p className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-blue-800">
        <Icon name="curve" className="h-3.5 w-3.5" />
        Measured
      </p>
      <h2 id="measured-heading" className="mt-5 font-serif text-3xl sm:text-4xl">
        Measured numbers
      </h2>
      <p className="mt-3 max-w-2xl leading-relaxed text-stone-600">
        None yet. After your first sales upload, each product gets a price elasticity with the range it could fall in.
        Nothing in this section is ever estimated from your profile.
      </p>
      <ul className="mt-6 grid gap-4 sm:grid-cols-3">
        {tiles.map((tile) => (
          <li key={tile.title} className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 p-5">
            <Icon name={tile.icon} className="h-5 w-5 text-stone-500" />
            <p className="mt-3 font-semibold text-stone-800">{tile.title}</p>
            <p className="mt-1 text-sm text-stone-600">{tile.needs}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}
