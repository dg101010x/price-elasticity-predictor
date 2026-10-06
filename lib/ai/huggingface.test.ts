import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_MODEL, ModelUnavailable, ROUTER_URL, chat } from './huggingface'
import { modelLabel } from './labels'

const messages = [{ role: 'user' as const, content: 'hi' }]

describe('chat', () => {
  beforeEach(() => {
    vi.stubEnv('HF_TOKEN', 'hf_test')
    vi.stubEnv('HF_MODEL', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('refuses to call out without a token', async () => {
    vi.stubEnv('HF_TOKEN', '')
    await expect(chat(messages)).rejects.toBeInstanceOf(ModelUnavailable)
  })

  it('posts an OpenAI-style request to the router and returns the reply', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ choices: [{ message: { content: '  - one\n- two  ' } }] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await chat(messages, { maxTokens: 50, temperature: 0.1 })
    expect(result).toEqual({ text: '- one\n- two', model: DEFAULT_MODEL })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(ROUTER_URL)
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer hf_test')
    expect(JSON.parse(init.body as string)).toEqual({ model: DEFAULT_MODEL, messages, max_tokens: 50, temperature: 0.1 })
  })

  it('uses HF_MODEL when set', async () => {
    vi.stubEnv('HF_MODEL', 'meta-llama/Llama-3.2-3B-Instruct:novita')
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ choices: [{ message: { content: 'ok' } }] })))
    vi.stubGlobal('fetch', fetchMock)
    const result = await chat(messages)
    expect(result.model).toBe('meta-llama/Llama-3.2-3B-Instruct:novita')
  })

  it('turns HTTP errors into ModelUnavailable with the status', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('model not supported', { status: 400 })))
    await expect(chat(messages)).rejects.toThrow('Hugging Face returned 400: model not supported')
  })

  it('rejects an empty reply', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ choices: [{ message: { content: '   ' } }] }))))
    await expect(chat(messages)).rejects.toThrow('empty reply')
  })

  it('wraps network failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('fetch failed'))))
    await expect(chat(messages)).rejects.toThrow('Hugging Face request failed: fetch failed')
  })
})

describe('modelLabel', () => {
  it('drops the org and provider suffix', () => {
    expect(modelLabel('meta-llama/Llama-3.1-8B-Instruct:novita')).toBe('Llama 3.1 8B Instruct')
  })
})
