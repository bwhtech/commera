// Product telemetry to Pulse. docs/telemetry.md is the only definition of an event's name and
// properties; an event that is not in its tables does not go out.
import { telemetryPlugin, useTelemetry as useFrameworkTelemetry } from '@framework/ui/telemetry/index.ts'
import { bootValue } from './data/boot'

// get_boot's `telemetry` key. Picked rather than spread, so a key added to the boot for another
// reason never rides every event.
const { app_version: appVersion, hosting } = bootValue('telemetry', {}) ?? {}
const sharedProperties = { app_version: appVersion, hosting }

// The plugin turns itself on only after it has fetched boot_config and imported the Pulse client,
// and drops every capture before that. OnboardingFlow sends its first event as it mounts, which is
// well inside that window, so captures wait for the install to settle.
let ready = Promise.resolve()

// Called instead of app.use() because app.use() throws the install's promise away.
export function installTelemetry(app, router) {
  ready = Promise.resolve(telemetryPlugin.install(app, { app_name: 'commera', router })).catch(() => {})
}

export function useTelemetry() {
  const telemetry = useFrameworkTelemetry()
  return {
    // Telemetry must never fail the action it reports on, so every error stops here.
    capture(event, properties = {}) {
      ready
        .then(() => telemetry.capture(event, { ...properties, ...sharedProperties }))
        .catch((error) => console.warn('[commera] telemetry capture failed', event, error))
    },
  }
}
