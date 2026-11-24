from commera.localization.boot_translations import clear_translation_version


def on_update(doc, method=None):
	clear_translation_version()


def on_trash(doc, method=None):
	clear_translation_version()
