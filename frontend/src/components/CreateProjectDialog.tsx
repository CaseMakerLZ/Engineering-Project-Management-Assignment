import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft,
  FolderInput,
  FolderOpen,
  FolderPlus,
  LoaderCircle,
} from 'lucide-react'
import { createProject } from '../api/projects'
import { IS_CLOUD_MODE } from '../config'
import { ApiError, describeError } from '../lib/errors'
import type { Project } from '../types/api'
import type { SelectedLocalDirectory } from '../types/files'
import { DirectoryPicker } from './DirectoryPicker'
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

type ProjectCreateMode = 'blank' | 'local' | null

export function CreateProjectDialog({ open, onClose, onCreated }: CreateProjectDialogProps) {
  const [mode, setMode] = useState<ProjectCreateMode>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedDirectory, setSelectedDirectory] = useState<SelectedLocalDirectory | null>(null)
  const [directoryNotice, setDirectoryNotice] = useState<string | null>(null)
  const [directoryPickerOpen, setDirectoryPickerOpen] = useState(false)
  const [createdProject, setCreatedProject] = useState<Project | null>(null)
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    if (!open) return
    setMode(null)
    setName('')
    setDescription('')
    setSelectedDirectory(null)
    setDirectoryNotice(null)
    setDirectoryPickerOpen(false)
    setCreatedProject(null)
    setErrors({})
    setSubmitting(false)
    submittingRef.current = false
  }, [open])

  const validate = (): FormErrors => {
    const next: FormErrors = {}
    if (!name.trim()) next.name = '请输入项目名称'
    else if (name.trim().length > 50) next.name = '项目名称不能超过 50 个字符'
    if (description.length > 200) next.description = '项目描述不能超过 200 个字符'
    if (!IS_CLOUD_MODE && !selectedDirectory) {
      next.localPath = '请先选择项目文件夹'
    }
    return next
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (submittingRef.current || createdProject) return
    const nextErrors = validate()
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    submittingRef.current = true
    setSubmitting(true)
    setErrors({})
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
        ...(IS_CLOUD_MODE
          ? {}
          : { local_path: selectedDirectory?.absolute_path }),
      })
      onCreated(project)
      onClose()
    } catch (error) {
      const message = describeError(error)
      const next: FormErrors = {
        form: IS_CLOUD_MODE ? message : `${message} 所选文件夹仍会保留。`,
      }
      if (
        error instanceof ApiError &&
        error.data &&
        typeof error.data === 'object' &&
        'project_id' in error.data &&
        typeof error.data.project_id === 'string'
      ) {
        setCreatedProject({
          project_id: error.data.project_id,
          name: name.trim(),
          description: description.trim(),
          local_path: selectedDirectory?.absolute_path ?? null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        next.form = '项目已经创建，但目录准备失败。可以进入项目后重试准备，不需要再次创建项目。'
      } else if (message.includes('目录')) next.localPath = message
      else if (message.includes('名称')) next.name = message
      setErrors(next)
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const chooseMode = (nextMode: Exclude<ProjectCreateMode, null>) => {
    setMode(nextMode)
    setErrors({})
    if (nextMode === 'local' && !IS_CLOUD_MODE) {
      setDirectoryPickerOpen(true)
    }
  }

  const goBackToModes = () => {
    setMode(null)
    setErrors({})
  }

  const modalTitle =
    mode === 'blank'
      ? '新建空白项目'
      : mode === 'local'
        ? '从本地文件夹创建'
        : '创建项目'
  const modalDescription =
    mode === 'blank'
      ? IS_CLOUD_MODE
        ? '创建一个新的云端工作区，之后可以在对话中让 Agent 生成项目文件。'
        : '为项目选择或创建一个本地文件夹，Agent 将直接在该目录中工作。'
      : mode === 'local'
        ? IS_CLOUD_MODE
          ? '从本机文件夹导入需要 Java 提供上传或工作区导入接口。'
          : '选择一个已有项目目录，文件保留在本机，不会复制或上传。'
        : '选择一个创建方式。新建项目不会覆盖已有目录。'

  const footer = createdProject ? (
    <>
      <button type="button" className="btn btn-ghost" onClick={onClose}>
        稍后处理
      </button>
      <button
        type="button"
        className="btn btn-primary"
        onClick={() => {
          onCreated(createdProject)
          onClose()
        }}
      >
        <FolderOpen size={16} />
        进入项目
      </button>
    </>
  ) : mode === null ? (
    <button type="button" className="btn btn-ghost" onClick={onClose}>
      取消
    </button>
  ) : (
    <>
      <button
        type="button"
        className="btn btn-ghost modal-footer-leading"
        onClick={goBackToModes}
        disabled={submitting}
      >
        <ArrowLeft size={15} />
        选择方式
      </button>
      <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
        取消
      </button>
      <button
        type="submit"
        className="btn btn-primary"
        form="create-project-form"
        disabled={submitting || (!IS_CLOUD_MODE && !selectedDirectory)}
      >
        {submitting ? (
          <LoaderCircle size={16} className="spin" />
        ) : mode === 'local' ? (
          <FolderOpen size={16} />
        ) : (
          <FolderPlus size={16} />
        )}
        {submitting
          ? '正在创建…'
          : mode === 'local'
            ? '绑定并创建项目'
            : '创建项目'}
      </button>
    </>
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={modalTitle}
      description={modalDescription}
      footer={footer}
    >
      {mode === null ? (
        <div className="project-create-mode-grid">
          <button
            type="button"
            className="project-create-mode-card"
            onClick={() => chooseMode('blank')}
          >
            <span className="project-create-mode-icon">
              <FolderPlus size={22} />
            </span>
            <span>
              <strong>新建空白项目</strong>
              <small>
                {IS_CLOUD_MODE
                  ? '创建独立云端工作区，不读取本机文件。'
                  : '选择或新建一个本地文件夹作为项目目录。'}
              </small>
            </span>
          </button>

          <button
            type="button"
            className="project-create-mode-card"
            onClick={() => chooseMode('local')}
            disabled={IS_CLOUD_MODE}
            title={
              IS_CLOUD_MODE
                ? '当前云端 Java 接口未提供本机文件上传或导入能力'
                : undefined
            }
          >
            <span className="project-create-mode-icon project-create-mode-icon-local">
              <FolderInput size={22} />
            </span>
            <span>
              <strong>从本地文件夹创建</strong>
              <small>
                {IS_CLOUD_MODE
                  ? '需要后端上传/导入接口，当前云端模式不可用。'
                  : '绑定已有项目目录，不复制或上传文件。'}
              </small>
            </span>
          </button>
        </div>
      ) : (
        <form id="create-project-form" className="form-stack" onSubmit={handleSubmit}>
          {mode === 'local' ? (
            <div className="project-create-source-note">
              <FolderInput size={17} />
              <div>
                <strong>使用已有本地文件夹</strong>
                <p>
                  Agent 会直接操作所选目录中的现有文件。项目名称会按文件夹名自动预填，之后仍可修改。
                </p>
              </div>
            </div>
          ) : null}

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
            {errors.description ? (
              <span className="field-error">{errors.description}</span>
            ) : null}
          </label>

          {!IS_CLOUD_MODE ? (
            <div className="field">
              <span className="field-label">
                项目文件夹 <em>本地模式必填</em>
              </span>
              <div className="selected-directory-control">
                <input
                  value={selectedDirectory?.absolute_path ?? ''}
                  readOnly
                  placeholder="尚未选择文件夹"
                  spellCheck={false}
                  aria-invalid={Boolean(errors.localPath)}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-small"
                  onClick={() => setDirectoryPickerOpen(true)}
                  disabled={submitting}
                >
                  <FolderOpen size={15} />
                  {selectedDirectory ? '重新选择' : '选择文件夹'}
                </button>
              </div>
              <span className="field-help">
                {mode === 'local'
                  ? '选择 Java 所在电脑上的已有项目目录。'
                  : '选择一个空目录，或在目录选择器中新建项目文件夹。'}
              </span>
              {directoryNotice ? (
                <span className="field-help directory-retained-note">{directoryNotice}</span>
              ) : null}
              {errors.localPath ? (
                <span className="field-error">{errors.localPath}</span>
              ) : null}
            </div>
          ) : null}

          {errors.form ? <div className="form-alert">{errors.form}</div> : null}
        </form>
      )}

      {!IS_CLOUD_MODE ? (
        <DirectoryPicker
          open={directoryPickerOpen}
          allowCreate={mode === 'blank'}
          initialRootId={selectedDirectory?.root_id}
          initialPath={selectedDirectory?.path}
          onClose={() => setDirectoryPickerOpen(false)}
          onFolderCreated={(directory) => {
            setDirectoryNotice(
              `文件夹“${directory.path.split('/').at(-1)}”已创建并保留。取消或保存失败不会删除它。`,
            )
          }}
          onSelect={(directory) => {
            setSelectedDirectory(directory)
            setDirectoryNotice(null)
            setDirectoryPickerOpen(false)
            if (mode === 'local' && !name.trim()) {
              setName(directory.path.split('/').filter(Boolean).at(-1) ?? '')
            }
            setErrors((current) => ({
              ...current,
              localPath: undefined,
              form: undefined,
            }))
          }}
        />
      ) : null}
    </Modal>
  )
}
