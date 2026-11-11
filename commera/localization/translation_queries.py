"""Database selection of catalog records, before loading their translation fields."""

import frappe
from frappe.query_builder import Criterion, DocType
from frappe.query_builder.functions import Count, IfNull

from commera.localization.content import DOCTYPE, Sha2
from commera.localization.resources import IMAGE, DoctypeResource


class RecordQuery:
	def __init__(self, resource, language):
		self.resource = resource
		self.record = DocType(resource.doctype)
		self.query = frappe.qb.from_(self.record)
		self.sources, self.translations = [], []
		kinds = resource.get_field_kinds()
		self.present, self.unfinished = [], []
		for index, field in enumerate(resource.fields):
			source = self.source(field)
			translation = DocType(DOCTYPE).as_("translation_" + str(index))
			self.query = self.query.left_join(translation).on(
				(translation.reference_doctype == resource.doctype)
				& (translation.reference_name == self.record.name)
				& (translation.reference_field == field)
				& (translation.language == language)
				& (IfNull(translation.market, "") == "")
			)
			present = IfNull(source, "") != ""
			missing = IfNull(translation.translated_value, "") == ""
			outdated = IfNull(translation.source_hash, "") != Sha2(source, 256)
			self.present.append(present)
			self.unfinished.append(
				present & ((~missing & outdated) if kinds.get(field) == IMAGE else (missing | outdated))
			)
			self.sources.append(source)
			self.translations.append(translation.translated_value)

	@classmethod
	def for_resource(cls, resource, language):
		if not isinstance(resource, DoctypeResource) or frappe.get_meta(resource.doctype).issingle:
			return None
		return cls(resource, language)

	def source(self, field):
		if frappe.get_meta(self.resource.doctype).has_field(field):
			return self.record[field]
		if (self.resource.doctype, field) == ("Shop Web Page", "title"):
			return self.record.name
		if (self.resource.doctype, field) == ("Style Attribute Variant", "description"):
			item = DocType("Item")
			self.query = self.query.left_join(item).on(item.name == self.record.item_style)
			return item.description
		raise ValueError("A database source is required for " + self.resource.doctype + "." + field)

	def matching(self, to_do):
		return self.query.where(Criterion.any(self.unfinished if to_do else self.present))

	def names(self, to_do, after, limit):
		query = self.matching(to_do).select(self.record.name).orderby(self.record.name).limit(limit)
		if after:
			query = query.where(self.record.name > after)
		return [row[0] for row in query.run()]

	def count(self, to_do):
		return self.matching(to_do).select(Count(self.record.name)).run()[0][0]

	def search(self, text, limit):
		pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
		matches = [
			present & (source.like(pattern) | translation.like(pattern))
			for present, source, translation in zip(
				self.present, self.sources, self.translations, strict=True
			)
		]
		return [
			row[0]
			for row in self.matching(False)
			.where(Criterion.any(matches))
			.select(self.record.name)
			.orderby(self.record.name)
			.limit(limit)
			.run()
		]
