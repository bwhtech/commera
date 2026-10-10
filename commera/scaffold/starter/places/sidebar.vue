<script>
export const plugin = { label: '$label' }
</script>

<script setup>
// Runs when the sidebar row is clicked. This one opens the plugin's tab in Settings.
import { usePlugin } from '@commera/admin'

usePlugin().openSettings()
</script>
