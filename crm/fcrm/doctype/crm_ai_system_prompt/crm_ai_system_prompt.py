# Copyright (c) 2024, Sinx Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMAISystemPrompt(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		prompt_name: DF.Data
		system_prompt: DF.TextEditor
	# end: auto-generated types

	def validate(self):
		if self.is_default:
			# Unset other defaults before saving the current one as default
			frappe.db.sql("""UPDATE `tabCRM AI System Prompt`
							SET `is_default` = 0
							WHERE `name` != %s AND `is_default` = 1""", self.name)
	pass 