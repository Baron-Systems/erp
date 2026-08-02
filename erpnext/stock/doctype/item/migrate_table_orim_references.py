import frappe
from frappe.utils import cint


def execute():
	"""Backfill item_price_reference for existing Child Item Price rows.

	Matches using the richest available field set to avoid linking the wrong
	record during migration. Reports ambiguous or unmatched rows clearly
	without auto-deleting any data.
	"""
	rows = frappe.db.get_all(
		"child item price",
		filters={
			"parenttype": "Item",
			"parentfield": "table_orim",
			"item_price_reference": ["is", "not set"],
		},
		fields=["name", "parent", "price_list", "uom", "rate"],
	)

	if not rows:
		print("No unlinked table_orim rows found. Migration is complete.")
		return

	# Build an index of all Item Prices keyed by the rich match fields
	price_fields = [
		"name", "item_code", "price_list", "uom", "price_list_rate",
		"currency", "buying", "selling",
	]
	price_index = {}
	for ip in frappe.db.get_all("Item Price", fields=price_fields):
		key = (
			ip.item_code,
			ip.price_list,
			ip.uom,
			ip.price_list_rate,
			ip.currency,
			cint(ip.buying),
			cint(ip.selling),
		)
		price_index.setdefault(key, []).append(ip.name)

	matches = []
	unmatched = []
	ambiguous = []

	for row in rows:
		price_list_data = frappe.db.get_value(
			"Price List",
			row["price_list"],
			["currency", "selling", "buying"],
			as_dict=True,
		)
		if not price_list_data:
			unmatched.append({**row, "reason": "Price List not found"})
			continue

		key = (
			row["parent"],
			row["price_list"],
			row["uom"],
			row["rate"],
			price_list_data.currency,
			cint(price_list_data.buying),
			cint(price_list_data.selling),
		)

		candidates = price_index.get(key, [])

		if len(candidates) == 1:
			matches.append((row["name"], candidates[0]))
		elif len(candidates) == 0:
			unmatched.append({**row, "reason": "No matching Item Price"})
		else:
			ambiguous.append({**row, "candidates": candidates})

	# Report ambiguous cases
	if ambiguous:
		lines = []
		for a in ambiguous:
			lines.append(
				f"{a['name']} | {a['parent']} | {a['price_list']} | {a['uom']} | {a['rate']} | "
				f"Candidates: {', '.join(a['candidates'])}"
			)
		if len(ambiguous) > 100:
			lines.append(f"... and {len(ambiguous) - 100} more ambiguous rows.")
		frappe.log_error(
			title="Ambiguous table_orim rows during migration",
			message="\n".join(lines[:100]),
		)

	# Report unmatched cases
	if unmatched:
		lines = []
		for u in unmatched:
			lines.append(
				f"{u['name']} | {u['parent']} | {u['price_list']} | {u['uom']} | {u['rate']} | "
				f"Reason: {u['reason']}"
			)
		if len(unmatched) > 100:
			lines.append(f"... and {len(unmatched) - 100} more unmatched rows.")
		frappe.log_error(
			title="Unmatched table_orim rows during migration",
			message="\n".join(lines[:100]),
		)

	if ambiguous or unmatched:
		print(f"Matched rows: {len(matches)}")
		print(f"Ambiguous rows: {len(ambiguous)}")
		print(f"Unmatched rows: {len(unmatched)}")
		frappe.throw(
			f"Migration aborted. Ambiguous: {len(ambiguous)} rows. "
			f"Unmatched: {len(unmatched)} rows. "
			"Check Error Log for details. Resolve before retrying."
		)

	for row_name, item_price_name in matches:
		frappe.db.set_value(
			"child item price",
			row_name,
			"item_price_reference",
			item_price_name,
			update_modified=False,
		)

	print(f"Migration complete: {len(matches)} rows linked.")
