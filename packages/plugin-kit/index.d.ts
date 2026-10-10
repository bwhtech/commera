export interface SidebarActionContext {
	/** Opens the plugin's own Settings tab, or a Commera tab such as 'payments'. */
	openSettings(tab?: string): void;
	/** Goes to a dashboard route; a relative path resolves against /commera/plugins/<app>/. */
	navigate(to: string): Promise<unknown>;
	/** Opens a URL in a new tab. */
	openUrl(url: string): void;
	toast: {
		success(message: string): void;
		error(message: string): void;
		warning(message: string): void;
		info(message: string): void;
	};
}

export interface SidebarAction {
	/** 1 to 40 lowercase letters, digits and hyphens; the entry's stable key. */
	name: string;
	label: string;
	/** A name from Commera's icon list, such as 'settings'. */
	icon?: string;
	order?: number;
	/** A DocType the user must be able to read to see the row. */
	requires?: string;
	/** A dotted path to a function in the plugin that returns a bool. */
	condition?: string;
	/** Runs when the row is clicked. */
	run(context: SidebarActionContext): void | Promise<void>;
}

export interface PluginConfig {
	/** Rows after the plugin's pages in its sidebar group. */
	sidebar?: SidebarAction[];
}

export function definePlugin(config: PluginConfig): PluginConfig;
