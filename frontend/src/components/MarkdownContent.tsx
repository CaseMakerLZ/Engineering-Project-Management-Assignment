import { memo, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { downloadProjectFile } from '../api/files'
import { describeError } from '../lib/errors'
import { parseProtectedDownloadLink } from '../lib/protectedLinks'
import { useToast } from './ToastProvider'
import 'katex/dist/katex.min.css'

function MarkdownLink({
  children,
  href,
}: {
  children: React.ReactNode
  href?: string
}) {
  const protectedFile =
    typeof window === 'undefined'
      ? null
      : parseProtectedDownloadLink(href, window.location.href)
  const { pushToast } = useToast()
  const [downloading, setDownloading] = useState(false)
  const downloadingRef = useRef(false)
  const downloadControllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      downloadControllerRef.current?.abort()
    }
  }, [])

  if (!protectedFile) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener">
        {children}
      </a>
    )
  }

  return (
    <a
      href={href}
      aria-busy={downloading}
      onClick={(event) => {
        event.preventDefault()
        if (downloadingRef.current) return
        downloadingRef.current = true
        const controller = new AbortController()
        downloadControllerRef.current = controller
        setDownloading(true)
        void downloadProjectFile(protectedFile.projectId, protectedFile.path, controller.signal)
          .catch((error: unknown) => {
            if (error instanceof DOMException && error.name === 'AbortError') return
            pushToast(describeError(error), 'error')
          })
          .finally(() => {
            downloadingRef.current = false
            downloadControllerRef.current = null
            if (mountedRef.current) setDownloading(false)
          })
      }}
    >
      {children}
      {downloading ? '（下载中…）' : ''}
    </a>
  )
}

export const MarkdownContent = memo(function MarkdownContent({
  content,
}: {
  content: string
}) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ children, href }) => <MarkdownLink href={href}>{children}</MarkdownLink>,
          table: ({ children }) => (
            <div className="markdown-table-wrap">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
