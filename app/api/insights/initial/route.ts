import { NextResponse, type NextRequest } from 'next/server'
import type { Business, Insight } from '@/lib/business'
import { generateInitialInsight } from '@/lib/insights/initial'
import { bearerToken, createAdminClient, createUserClient } from '@/lib/supabase-server'

export const maxDuration = 30

const REWRITE_COOLDOWN_MS = 60_000

function fail(status: number, error: string) {
  return NextResponse.json({ error }, { status })
}

export async function POST(request: NextRequest) {
  const token = bearerToken(request.headers.get('authorization'))
  if (!token) return fail(401, 'Sign in again to continue.')

  const supabase = createUserClient(token)
  const { data: auth, error: authError } = await supabase.auth.getUser(token)
  if (authError || !auth.user) return fail(401, 'Sign in again to continue.')

  let body: { businessId?: unknown; force?: unknown } = {}
  try {
    body = await request.json()
  } catch {
    return fail(400, 'Send a JSON body with a businessId.')
  }
  if (typeof body.businessId !== 'string') return fail(400, 'Send a JSON body with a businessId.')
  const force = body.force === true

  // RLS limits this to businesses the caller belongs to.
  const { data: business, error: businessError } = await supabase
    .from('businesses')
    .select('*')
    .eq('id', body.businessId)
    .maybeSingle<Business>()
  if (businessError) return fail(500, 'Could not load your business.')
  if (!business) return fail(404, 'Business not found.')

  const { data: latest } = await supabase
    .from('ai_insights')
    .select('*')
    .eq('business_id', business.id)
    .eq('scope', 'initial')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle<Insight>()

  if (latest) {
    const age = Date.now() - new Date(latest.created_at).getTime()
    const fresh = new Date(latest.created_at) >= new Date(business.updated_at)
    if ((fresh && !force) || age < REWRITE_COOLDOWN_MS) {
      return NextResponse.json({ insight: latest, persisted: true })
    }
  }

  const { name, city, region, country, industry, description, competition_scope, key_components } = business
  const result = await generateInitialInsight({
    name,
    city,
    region,
    country,
    industry,
    description,
    competition_scope,
    key_components,
  })
  const row = {
    business_id: business.id,
    scope: 'initial' as const,
    body: result.points.join('\n'),
    model: result.model,
    grounding: result.grounding,
  }

  const admin = createAdminClient()
  if (admin) {
    const { data: saved, error: saveError } = await admin.from('ai_insights').insert(row).select().single<Insight>()
    if (saved) return NextResponse.json({ insight: saved, persisted: true })
    console.error('Could not store initial insight:', saveError?.message)
  }

  const unsaved: Insight = { ...row, id: null, created_at: new Date().toISOString() }
  return NextResponse.json({ insight: unsaved, persisted: false })
}
