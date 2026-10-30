export class ApiError extends Error {
  readonly status: number
  readonly code?: number
  readonly data: unknown

  constructor(message: string, status: number, code?: number, data?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.data = data
  }
}

const ERROR_MESSAGES: Record<number, string> = {
  10001: '输入内容不符合要求，请检查后重试。',
  10002: '登录状态已失效，请重新登录。',
  10003: '你没有权限访问该资源。',
  10004: '项目、对话或任务不存在，或已被删除。',
  10005: '资源状态已发生变化，请刷新后重试。',
  10006: '实时连接数已达到上限，请保留当前连接并稍后重试。',
  20001: '用户名已存在，请更换一个。',
  20002: '用户名或密码错误。',
  30003: '项目不存在或已被删除。',
  30004: '对话不存在或已被删除。',
  30005: '当前对话已有任务正在执行，请等待完成后再提交。',
  30006: '任务不存在或已被删除。',
  30007: '项目正在执行其他任务，请等待结束后再试。',
  30008: '文件不存在或尚未发布。',
  40001: 'Agent 服务暂时不可用，请稍后重试。',
  40002: 'Agent 响应超时，请稍后重试。',
  40005: '当前执行容量已满，请稍后再试。',
  40006: '文件服务暂时不可用，请稍后重试。',
  50000: '系统内部错误，请稍后重试。',
  90001: '系统内部错误，请稍后重试。',
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 10001 || error.code === 20001) {
      return error.message || ERROR_MESSAGES[error.code]
    }
    if (error.code !== undefined && ERROR_MESSAGES[error.code]) {
      return ERROR_MESSAGES[error.code]
    }
    return error.message || `请求失败（HTTP ${error.status}）`
  }
  if (error instanceof TypeError) {
    return '无法连接服务器，请检查后端是否已启动。'
  }
  if (error instanceof Error && error.name === 'AbortError') {
    return '请求超时，请稍后重试。'
  }
  if (error instanceof Error) {
    return error.message
  }
  return '发生了未知错误，请稍后重试。'
}

export function isResourceNotFound(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 ||
      error.code === 10004 ||
      error.code === 30003 ||
      error.code === 30004 ||
      error.code === 30008)
  )
}
