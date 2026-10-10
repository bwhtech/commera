import { toast } from 'frappe-ui'
import { appLocation, settingsTabValue } from '../ia/plugins'
import { openSettings } from '../ia/settingsRoute'

// A sidebar action is an item in the plugin's commera/plugin.config.ts. The build ships that file as one module;
// a click imports it, finds the item by name and calls its run() with what a row can do.
export async function runSidebarAction(entry) {
  const { app, place, name, module_url, label } = entry
  try {
    if (entry.error || !module_url) throw new Error(entry.error || 'This plugin has not been built yet.')
    const url = import.meta.env.DEV ? `/@commera-plugin/${app}/${place}/${name}` : module_url
    const config = (await import(/* @vite-ignore */ url)).default
    const action = config?.[place]?.find((item) => item.name === name)
    if (!action) throw new Error(`${name} is not in ${app}'s plugin.config`)
    await action.run({
      openSettings: (tab) => openSettings(tab ?? settingsTabValue(app)),
      // Imported on use: router.js imports ia/plugins, which imports this file.
      navigate: async (to) => (await import('../router')).router.push(appLocation(app, to)),
      openUrl: (target) => window.open(target, '_blank', 'noopener'),
      toast,
    })
  } catch (error) {
    console.error(`[commera plugin ${entry.key}]`, error)
    toast.error(`${label} couldn't run`)
  }
}
