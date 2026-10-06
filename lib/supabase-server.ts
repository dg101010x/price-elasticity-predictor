import { createClient, type SupabaseClient } from '@supabase/supabase-js'

const serverAuth = { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }

function supabaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  if (!url) throw new Error('NEXT_PUBLIC_SUPABASE_URL is not set')
  return url
}

export function createUserClient(accessToken: string): SupabaseClient {
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!anonKey) throw new Error('NEXT_PUBLIC_SUPABASE_ANON_KEY is not set')
  return createClient(supabaseUrl(), anonKey, {
    global: { headers: { Authorization: `Bearer ${accessToken}` } },
    auth: serverAuth,
  })
}

// Writes to computed_results and ai_insights bypass RLS, so they only happen server-side.
export function createAdminClient(): SupabaseClient | null {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!serviceKey) return null
  return createClient(supabaseUrl(), serviceKey, { auth: serverAuth })
}

export function bearerToken(header: string | null): string | null {
  const match = header?.match(/^Bearer\s+(.+)$/i)
  return match ? match[1].trim() : null
}
