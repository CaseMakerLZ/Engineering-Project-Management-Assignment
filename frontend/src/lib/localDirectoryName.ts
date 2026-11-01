export function validateLocalDirectoryName(name: string): string | null {
  const trimmed = name.trim()
  if (!trimmed) return '请输入文件夹名称'
  if (trimmed === '.' || trimmed === '..') return '文件夹名称不能是点号'
  if (/[\\/:*?"<>|\u0000-\u001f]/.test(trimmed)) return '名称不能包含路径分隔符或特殊字符'
  if (/[ .]$/.test(trimmed)) return '名称不能以空格或句点结尾'
  if (
    /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i.test(trimmed)
  ) {
    return '该名称是 Windows 保留名称'
  }
  if (trimmed.length > 100) return '名称不能超过 100 个字符'
  return null
}
