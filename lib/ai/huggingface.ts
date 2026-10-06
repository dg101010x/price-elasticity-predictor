// The only module that talks to a language model. Swap providers here without touching callers.

export const ROUTER_URL = 'https://router.huggingface.co/v1/chat/completions'
export const DEFAULT_MODEL = 'meta-llama/Llama-3.1-8B-Instruct'

export type ChatMessage = { role: 'system' | 'user' | 'assistant'; content: string }

export type ChatOptions = { maxTokens?: number; temperature?: number; timeoutMs?: number }

export type ChatResult = { text: string; model: string }

export class ModelUnavailable extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ModelUnavailable'
  }
}

export async function chat(messages: ChatMessage[], options: ChatOptions = {}): Promise<ChatResult> {
  const token = process.env.HF_TOKEN
  if (!token) throw new ModelUnavailable('HF_TOKEN is not set')
  const model = process.env.HF_MODEL || DEFAULT_MODEL
  const { maxTokens = 400, temperature = 0.4, timeoutMs = 20_000 } = options

  let res: Response
  try {
    res = await fetch(ROUTER_URL, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages, max_tokens: maxTokens, temperature }),
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (err) {
    throw new ModelUnavailable(`Hugging Face request failed: ${(err as Error).message}`)
  }

  if (!res.ok) {
    const detail = (await res.text().catch(() => '')).slice(0, 200)
    throw new ModelUnavailable(`Hugging Face returned ${res.status}${detail ? `: ${detail}` : ''}`)
  }

  const data = (await res.json().catch(() => null)) as {
    model?: string
    choices?: { message?: { content?: unknown } }[]
  } | null
  const text = data?.choices?.[0]?.message?.content
  if (typeof text !== 'string' || !text.trim()) throw new ModelUnavailable('Hugging Face returned an empty reply')
  return { text: text.trim(), model }
}
