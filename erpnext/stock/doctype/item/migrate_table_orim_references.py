import frappe


def execute():
	"""Backfill item_price_reference for existing Child Item Price rows."""
	duplicates = report_duplicates()

	if duplicates:
		frappe.throw(
			"Duplicate Item Price records found. "
			f"{len(duplicates)} combinations have duplicates. "
			"Resolve duplicates before running migration. "
			"Check Error Log for details."
		)

	rows = frappe.db.get_all(
		"child item price",
		filters={
			"parenttype": "Item",
			"parentfield": "table_orim",
			"item_price_reference": ["is", "not set"],
		},
		fields=["name", "parent", "price_list", "uom"],
	)

	matches = []
	unmatched = []

	for row in rows:
		item_price_name = frappe.db.get_value(
			"Item Price",
			{
				"item_code": row["parent"],
				"price_list": row["price_list"],
				"uom": row["uom"],
			},
			"name",
		)

		if not item_price_name:
			unmatched.append(row)
			continue

		matches.append((row["name"], item_price_name))

	if unmatched:
		rows_to_log = unmatched[:100]
		message = "\n".join(
			f"{row['name']} | {row['parent']} | "
			f"{row['price_list']} | {row['uom']}"
			for row in rows_to_log
		)
		if len(unmatched) > 100:
			message += f"\n... and {len(unmatched) - 100} more rows."

		frappe.log_error(
			title="Unmatched table_orim rows during migration",
			message=message,
		)
		print(f"Matched rows: {len(matches)}")
		print(f"Unmatched rows: {len(unmatched)}")
		frappe.throw(
			f"{len(unmatched)} table_orim rows could not be linked to an Item Price. "
			"No rows were updated. Check Error Log for details."
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


def report_duplicates():
	"""Detect and log duplicate Item Price records before migration."""
	duplicates = frappe.db.sql(
		"""
		SELECT item_code, price_list, uom, COUNT(*) as cnt,
		       GROUP_CONCAT(name) as names
		FROM `tabItem Price`
		GROUP BY item_code, price_list, uom
		HAVING cnt > 1
		""",
		as_dict=True,
	)

	if duplicates:
		frappe.log_error(
			"Duplicate Item Price records found before migration. "
			+ " | ".join(
				f"{d.item_code}/{d.price_list}/{d.uom}: {d.names}"
				for d in duplicates
			)
		)
		print(f"WARNING: {len(duplicates)} duplicate Item Price combinations found.")
		print("Check Error Log for details before proceeding.")
	else:
		print("No duplicate Item Price records found. Migration is safe.")

	return duplicates
