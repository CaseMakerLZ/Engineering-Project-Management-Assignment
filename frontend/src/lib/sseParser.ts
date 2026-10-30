import type {
  TurnEventFrame,
  TurnEventName,
  TurnEventPayload,
} from '../types/turnEvents'

const DEFAULT_MAX_FRAME_CHARS = 1_000_000

export class SSEProtocolError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SSEProtocolError'
  }
}

export class SSEIdleTimeoutError extends Error {
  constructor() {
    super('实时连接长时间没有收到数据。')
    this.name = 'SSEIdleTimeoutError'
  }
}

function parseFrame(
  rawFrame: string,
  maxFrameChars: number,
): TurnEventFrame | null {
  if (rawFrame.length > maxFrameChars) {
    throw new SSEProtocolError('单条实时事件超过允许大小，已停止连接。')
  }
  const lines = rawFrame.split('\n')
  let eventName = ''
  let id: string | undefined
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    let value = separator === -1 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventName = value
    else if (field === 'id') id = value
    else if (field === 'data') dataLines.push(value)
  }

  if (!eventName || dataLines.length === 0) return null
  let data: TurnEventPayload
  try {
    data = JSON.parse(dataLines.join('\n')) as TurnEventPayload
  } catch {
    throw new SSEProtocolError(`SSE 事件 ${eventName} 的 JSON 数据不完整。`)
  }
  if (!data || typeof data !== 'object') {
    throw new SSEProtocolError(`SSE 事件 ${eventName} 缺少数据对象。`)
  }

  return {
    event: eventName as TurnEventName,
    id,
    data,
  }
}

export class SSEFrameParser {
  private buffer = ''
  private readonly maxFrameChars: number

  constructor(maxFrameChars = DEFAULT_MAX_FRAME_CHARS) {
    this.maxFrameChars = maxFrameChars
  }

  push(text: string): TurnEventFrame[] {
    this.buffer += text
    return this.consume(false)
  }

  finish(): TurnEventFrame[] {
    return this.consume(true)
  }

  private consume(flush: boolean): TurnEventFrame[] {
    this.buffer = this.buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const parts = this.buffer.split('\n\n')
    const pending = parts.pop() ?? ''
    if (flush) {
      if (pending.trim()) parts.push(pending)
      this.buffer = ''
    } else {
      this.buffer = pending
    }
    if (this.buffer.length > this.maxFrameChars) {
      throw new SSEProtocolError('单条实时事件超过允许大小，已停止连接。')
    }

    return parts
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => parseFrame(part, this.maxFrameChars))
      .filter((frame): frame is TurnEventFrame => frame !== null)
  }
}

export async function* readSSEStream(
  stream: ReadableStream<Uint8Array>,
  idleTimeoutMs = 60_000,
): AsyncGenerator<TurnEventFrame> {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8')
  const parser = new SSEFrameParser()

  try {
    while (true) {
      let timer: number | undefined
      const { done, value } = await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => {
          timer = globalThis.setTimeout(
            () => reject(new SSEIdleTimeoutError()),
            idleTimeoutMs,
          )
        }),
      ]).finally(() => {
        if (timer !== undefined) globalThis.clearTimeout(timer)
      })
      if (done) break
      for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
        yield frame
      }
    }
    const tail = decoder.decode()
    if (tail) {
      for (const frame of parser.push(tail)) yield frame
    }
    for (const frame of parser.finish()) yield frame
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
