import frappeUIPreset from 'frappe-ui/tailwind';

export default {
	presets: [frappeUIPreset],
	content: ['./src/**/*.{vue,js}'],
	// the editor already applies the base styles, and a second reset would restyle it
	corePlugins: { preflight: false },
};
