import { execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { BENCH, readPluginApps } from './pluginApps.js'

// Runs after the dashboard build, because each plugin checks its classes and imports against what that build wrote.
const failed = []
for (const app of readPluginApps()) {
  const appRoot = join(BENCH, 'apps', app)
  if (!existsSync(join(appRoot, 'package.json'))) continue
  console.log(`\nBuilding Commera plugin ${app}`)
  try {
    if (!existsSync(join(appRoot, 'node_modules'))) execSync('yarn install --frozen-lockfile', { cwd: appRoot, stdio: 'inherit' })
    execSync('yarn build', { cwd: appRoot, stdio: 'inherit' })
  } catch {
    failed.push(app)
  }
}

if (failed.length) {
  console.error(`\nCommera plugins that failed to build: ${failed.join(', ')}`)
  process.exit(1)
}
