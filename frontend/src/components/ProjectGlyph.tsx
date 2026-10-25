interface ProjectGlyphProps {
  projectId: string
  name: string
  size?: 'small' | 'default' | 'large'
}

function hueFromId(value: string): number {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) % 360
  }
  return hash
}

export function ProjectGlyph({ projectId, name, size = 'default' }: ProjectGlyphProps) {
  const initial = name.trim().slice(0, 1).toUpperCase() || 'P'
  const hue = hueFromId(projectId)
  return (
    <span
      className={`project-glyph project-glyph-${size}`}
      style={{
        background: `linear-gradient(145deg, hsl(${hue} 82% 62%), hsl(${(hue + 38) % 360} 70% 46%))`,
      }}
      aria-hidden="true"
    >
      {initial}
    </span>
  )
}
