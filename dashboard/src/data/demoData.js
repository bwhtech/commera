import { dialog, toast } from 'frappe-ui'
import { useAdminAction } from './api'

export const installDemoDataAction = useAdminAction('settings.install_demo_data')

// The seeder rewrites the homepage, the footer, the store currency and the payment accounts,
// so the confirmation names those rather than only the catalogue it also creates.
export function confirmInstallDemoData() {
  dialog.confirm({
    title: 'Replace this store with demo data?',
    message:
      'It seeds a full demo catalogue, and overwrites your homepage, footer, store currency and payment accounts. Run it on a store you have not set up yet.',
    theme: 'red',
    confirmLabel: 'Install demo data',
    onConfirm: async () => {
      // The palette can reopen this dialog while a run is still queuing; one seed job at a time.
      if (installDemoDataAction.loading) return
      try {
        await installDemoDataAction.submit()
      } catch {
        // useAdminAction has already toasted a refusal; a second toast here would stack on it.
        return
      }
      toast.success('Demo data queued', {
        description: 'It runs in the background and takes a few minutes.',
      })
    },
  })
}
