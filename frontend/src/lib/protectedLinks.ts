export function parseProtectedDownloadLink(
  href: string | undefined,
  currentHref: string,
): { projectId: string; path: string } | null {
  if (!href) return null
  let base: URL
  let url: URL
  try {
    base = new URL(currentHref)
    url = new URL(href, base)
  } catch {
    return null
  }
  if (url.origin !== base.origin) return null
  const match = url.pathname.match(/^\/api\/projects\/([^/]+)\/files\/download$/)
  if (!match) return null
  const path = url.searchParams.get('path')
  if (!path) return null
  try {
    return { projectId: decodeURIComponent(match[1]), path }
  } catch {
    return null
  }
}
