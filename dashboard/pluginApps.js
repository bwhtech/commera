import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const BENCH = fileURLToPath(new URL('../../..', import.meta.url))
// Outside the emptied outDir: bench builds apps in parallel, and the plugin kit reads these while commera rebuilds.
export const PLUGIN_HOST_DIR = fileURLToPath(new URL('../commera/public/plugin-host', import.meta.url))
export const OFFICIAL_DIR = fileURLToPath(new URL('../official_plugins', import.meta.url))
const OFFICIAL_OUT_DIR = fileURLToPath(new URL('../commera/public/official_plugins', import.meta.url))

export function readPluginApps() {
  const appsFile = join(BENCH, 'sites', 'apps.txt')
  if (!existsSync(appsFile)) return []
  return readFileSync(appsFile, 'utf8')
    .split('\n')
    .map((app) => app.trim())
    .filter((app) => app && app !== 'commera' && existsSync(sourceDirOf(app)))
}

function ownSourceDirOf(app) {
  return join(BENCH, 'apps', app, 'commera')
}

// An app's own commera/ folder wins, so an app that ships its own plugin replaces the one Commera ships for it.
export function isOfficialPlugin(app) {
  return !existsSync(ownSourceDirOf(app)) && existsSync(join(OFFICIAL_DIR, app))
}

export function sourceDirOf(app) {
  return isOfficialPlugin(app) ? join(OFFICIAL_DIR, app) : ownSourceDirOf(app)
}

export function outDirOf(app) {
  return isOfficialPlugin(app) ? join(OFFICIAL_OUT_DIR, app) : join(BENCH, 'apps', app, app, 'public', 'commera')
}

export function buildCommandOf(app) {
  return isOfficialPlugin(app)
    ? { command: 'node', args: ['build.js', app], cwd: OFFICIAL_DIR }
    : { command: 'yarn', args: ['build'], cwd: join(BENCH, 'apps', app) }
}
