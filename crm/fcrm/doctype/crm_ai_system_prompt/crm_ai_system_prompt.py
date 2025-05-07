import frappe
from frappe.model.document import Document

class CRMAISystemPrompt(Document):
    def validate(self):
        if self.is_default:
            # Unset other defaults before saving the current one as default
            frappe.db.sql("""UPDATE `tabCRM AI System Prompt`
                            SET `is_default` = 0
                            WHERE `name` != %s AND `is_default` = 1""", self.name) 