import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const BENCH = fileURLToPath(new URL('../../..', import.meta.url))

export function readPluginApps() {
  const appsFile = join(BENCH, 'sites', 'apps.txt')
  if (!existsSync(appsFile)) return []
  return readFileSync(appsFile, 'utf8')
    .split('\n')
    .map((app) => app.trim())
    .filter((app) => app && app !== 'commera' && existsSync(sourceDirOf(app)))
}

export function sourceDirOf(app) {
  return join(BENCH, 'apps', app, 'commera')
}
