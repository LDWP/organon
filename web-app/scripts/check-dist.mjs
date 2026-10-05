// Fails if the committed dist/ differs from a fresh build of src/.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function files(root, dir = '') {
  return readdirSync(join(root, dir), { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    return entry.isDirectory() ? files(root, path) : [path]
  })
}

const fresh = mkdtempSync(join(tmpdir(), 'organon-dist-'))
try {
  const vite = join('node_modules', 'vite', 'bin', 'vite.js')
  execFileSync(process.execPath, [vite, 'build', '--outDir', fresh, '--emptyOutDir'], { stdio: 'ignore' })
  const committed = new Set(files('dist'))
  const built = new Set(files(fresh))
  const stale = [...new Set([...committed, ...built])].filter(
    (path) =>
      !committed.has(path) ||
      !built.has(path) ||
      !readFileSync(join('dist', path)).equals(readFileSync(join(fresh, path))),
  )
  if (stale.length) {
    console.error(`dist/ is stale, run "npm run build" and commit:\n  ${stale.join('\n  ')}`)
    process.exitCode = 1
  }
} finally {
  rmSync(fresh, { recursive: true, force: true })
}
