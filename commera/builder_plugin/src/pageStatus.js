// the editor's page status dots: filled is live, hollow is a draft or edits waiting to publish
export const STATUS_DOTS = {
	Published: 'bg-current text-ink-green-7',
	Edited: 'border-[1.5px] border-current text-ink-green-7',
	Draft: 'border-[1.5px] border-current text-ink-gray-4',
	Empty: 'border-[1.5px] border-dashed border-current text-ink-gray-4',
};

export const STATUS_HINTS = {
	Published: 'Published',
	Edited: 'Published, with changes not published yet',
	Draft: 'Not published yet',
	Empty: 'Nothing on this page yet, so the store shows the parent theme here',
};

export function pageStatus(page) {
	if (!page.is_published) return page.is_empty ? 'Empty' : 'Draft';
	return page.has_unpublished_changes ? 'Edited' : 'Published';
}
