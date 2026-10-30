import type { TaskStatus } from '../types/api'
import type {
  TurnDisplayMessage,
  TurnEventFrame,
  TurnStreamState,
  TurnToolState,
} from '../types/turnEvents'

function normalizeMessages(value: unknown): TurnDisplayMessage[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((message) => {
    if (!message || typeof message !== 'object') return []
    const item = message as { message_id?: unknown; text?: unknown }
    if (typeof item.message_id !== 'string' || typeof item.text !== 'string') return []
    return [{ message_id: item.message_id, text: item.text }]
  })
}

function updateTool(
  tools: TurnToolState[],
  callId: string,
  update: Partial<TurnToolState>,
): TurnToolState[] {
  const index = tools.findIndex((tool) => tool.call_id === callId)
  if (index === -1) return tools
  const next = [...tools]
  next[index] = { ...next[index], ...update }
  return next
}

export function reduceTurnEvent(
  current: TurnStreamState,
  frame: TurnEventFrame,
): TurnStreamState {
  const data = frame.data as unknown as Record<string, unknown>
  const sequence =
    typeof data.sequence === 'number' && Number.isFinite(data.sequence)
      ? data.sequence
      : current.sequence

  if (frame.event === 'stream.error') {
    return {
      ...current,
      sequence: Math.max(current.sequence, sequence),
      channelError:
        typeof data.message === 'string' && data.message.trim()
          ? data.message
          : '实时连接发生错误。',
    }
  }

  if (sequence <= current.sequence) return current
  const next: TurnStreamState = { ...current, sequence }

  if (frame.event === 'run.snapshot') {
    const status =
      typeof data.status === 'string' ? (data.status as TaskStatus) : current.status
    const activeTool =
      data.active_tool && typeof data.active_tool === 'object'
        ? (data.active_tool as TurnToolState)
        : null
    return {
      ...next,
      status,
      messages: normalizeMessages(data.messages),
      activeTool: activeTool
        ? {
            call_id: activeTool.call_id,
            tool_name: activeTool.tool_name,
          }
        : null,
      tools: activeTool
        ? [{ call_id: activeTool.call_id, tool_name: activeTool.tool_name }]
        : [],
      result: typeof data.result === 'string' ? data.result : null,
      error: typeof data.error === 'string' ? data.error : null,
      channelError: null,
    }
  }

  if (frame.event === 'run.started') {
    return { ...next, status: 'RUNNING', channelError: null }
  }

  if (frame.event === 'assistant.delta') {
    const messageId = typeof data.message_id === 'string' ? data.message_id : ''
    const delta = typeof data.delta === 'string' ? data.delta : ''
    if (!messageId || !delta) return next
    const index = next.messages.findIndex((message) => message.message_id === messageId)
    const messages = [...next.messages]
    if (index === -1) messages.push({ message_id: messageId, text: delta })
    else messages[index] = { ...messages[index], text: messages[index].text + delta }
    return { ...next, messages, status: 'RUNNING' }
  }

  if (frame.event === 'tool.started') {
    const callId = typeof data.call_id === 'string' ? data.call_id : ''
    const toolName = typeof data.tool_name === 'string' ? data.tool_name : ''
    if (!callId || !toolName) return next
    const tool = { call_id: callId, tool_name: toolName }
    const exists = next.tools.some((item) => item.call_id === callId)
    return {
      ...next,
      status: 'RUNNING',
      activeTool: tool,
      tools: exists
        ? updateTool(next.tools, callId, tool)
        : [...next.tools, tool],
    }
  }

  if (frame.event === 'tool.finished') {
    const callId = typeof data.call_id === 'string' ? data.call_id : ''
    if (!callId) return next
    return {
      ...next,
      status: 'RUNNING',
      activeTool:
        next.activeTool?.call_id === callId ? null : next.activeTool,
      tools: updateTool(next.tools, callId, {
        success: data.success === true,
        error_code: typeof data.error_code === 'string' ? data.error_code : null,
        error: typeof data.error === 'string' ? data.error : null,
      }),
    }
  }

  if (
    frame.event === 'run.completed' ||
    frame.event === 'run.failed' ||
    frame.event === 'run.cancelled'
  ) {
    const fallbackStatus: TaskStatus =
      frame.event === 'run.completed'
        ? 'COMPLETED'
        : frame.event === 'run.failed'
          ? 'FAILED'
          : 'CANCELLED'
    return {
      ...next,
      status:
        typeof data.status === 'string'
          ? (data.status as TaskStatus)
          : fallbackStatus,
      activeTool: null,
      result: typeof data.result === 'string' ? data.result : null,
      error: typeof data.error === 'string' ? data.error : null,
    }
  }

  return next
}
