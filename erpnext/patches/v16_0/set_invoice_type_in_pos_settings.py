import frappe


def execute():
	# Check if column exists first to avoid migration errors
	if not frappe.db.has_column("POS Settings", "invoice_type"):
		return
	
	if not frappe.db.get_single_value("POS Settings", "invoice_type"):
		frappe.db.set_single_value("POS Settings", "invoice_type", "POS Invoice")
