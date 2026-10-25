import { useEffect, useState } from 'react'
import { FolderPlus, LoaderCircle } from 'lucide-react'
import { createProject } from '../api/projects'
import { IS_CLOUD_MODE } from '../config'
import { describeError } from '../lib/errors'
import type { Project } from '../types/api'
import { Modal } from './Modal'

interface CreateProjectDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (project: Project) => void
}

interface FormErrors {
  name?: string
  description?: string
  localPath?: string
  form?: string
}

export function CreateProjectDialog({ open, onClose, onCreated }: CreateProjectDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [localPath, setLocalPath] = useState('')
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setName('')
    setDescription('')
    setLocalPath('')
    setErrors({})
    setSubmitting(false)
  }, [open])

  const validate = (): FormErrors => {
    const next: FormErrors = {}
    if (!name.trim()) next.name = '请输入项目名称'
    else if (name.trim().length > 50) next.name = '项目名称不能超过 50 个字符'
    if (description.length > 200) next.description = '项目描述不能超过 200 个字符'
    if (!IS_CLOUD_MODE && !localPath.trim()) next.localPath = '本地模式需要填写项目目录'
    return next
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (submitting) return
    const nextErrors = validate()
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    setSubmitting(true)
    setErrors({})
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
        ...(IS_CLOUD_MODE ? {} : { local_path: localPath.trim() }),
      })
      onCreated(project)
      onClose()
    } catch (error) {
      const message = describeError(error)
      const next: FormErrors = { form: message }
      if (message.includes('目录')) next.localPath = message
      else if (message.includes('名称')) next.name = message
      setErrors(next)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="创建新项目"
      description="项目用来组织同一目标下的多段 Agent 对话。"
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            form="create-project-form"
            disabled={submitting}
          >
            {submitting ? <LoaderCircle size={16} className="spin" /> : <FolderPlus size={16} />}
            {submitting ? '正在创建…' : '创建项目'}
          </button>
        </>
      }
    >
      <form id="create-project-form" className="form-stack" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">
            项目名称 <em>必填</em>
          </span>
          <input
            autoFocus
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setErrors((current) => ({ ...current, name: undefined, form: undefined }))
            }}
            placeholder="例如：课程项目 Agent"
            maxLength={50}
            aria-invalid={Boolean(errors.name)}
          />
          <span className="field-help">1–50 个字符</span>
          {errors.name ? <span className="field-error">{errors.name}</span> : null}
        </label>

        <label className="field">
          <span className="field-label">项目描述</span>
          <textarea
            value={description}
            onChange={(event) => {
              setDescription(event.target.value)
              setErrors((current) => ({ ...current, description: undefined, form: undefined }))
            }}
            placeholder="简单说明这个项目要解决的问题（选填）"
            rows={3}
            maxLength={200}
          />
          <span className="field-help">{description.length} / 200</span>
          {errors.description ? <span className="field-error">{errors.description}</span> : null}
        </label>

        {!IS_CLOUD_MODE ? (
          <label className="field">
            <span className="field-label">
              项目目录 <em>本地模式必填</em>
            </span>
            <input
              value={localPath}
              onChange={(event) => {
                setLocalPath(event.target.value)
                setErrors((current) => ({ ...current, localPath: undefined, form: undefined }))
              }}
              placeholder="例如：C:\workspace\my-project"
              spellCheck={false}
              aria-invalid={Boolean(errors.localPath)}
            />
            <span className="field-help">填写 Java 后端所在机器上真实存在的目录路径。</span>
            {errors.localPath ? <span className="field-error">{errors.localPath}</span> : null}
          </label>
        ) : null}

        {errors.form ? <div className="form-alert">{errors.form}</div> : null}
      </form>
    </Modal>
  )
}
