import { execFileSync, execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { buildCommandOf, readPluginApps } from './pluginApps.js'

// Runs after the dashboard build, because each plugin checks its classes and imports against what that build wrote.
const failed = []
for (const app of readPluginApps()) {
  const { command, args, cwd } = buildCommandOf(app)
  if (!existsSync(join(cwd, 'package.json'))) continue
  console.log(`\nBuilding Commera plugin ${app}`)
  try {
    if (!existsSync(join(cwd, 'node_modules'))) execSync('yarn install --frozen-lockfile', { cwd, stdio: 'inherit' })
    execFileSync(command, args, { cwd, stdio: 'inherit' })
  } catch {
    failed.push(app)
  }
}

if (failed.length) {
  console.error(`\nCommera plugins that failed to build: ${failed.join(', ')}`)
  process.exit(1)
}
