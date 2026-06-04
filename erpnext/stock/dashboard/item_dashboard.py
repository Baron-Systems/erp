import frappe
from frappe.desk.reportview import build_match_conditions
from frappe.utils import cint, escape_html, flt

from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
	get_sre_reserved_qty_for_items_and_warehouses as get_reserved_stock_details,
)


@frappe.whitelist()
def get_data(
	item_code=None, warehouse=None, item_group=None, start=0, sort_by="actual_qty", sort_order="desc"
):
	"""Return data to render the item dashboard"""
	filters = []
	if item_code:
		filters.append(["item_code", "=", item_code])
	if warehouse:
		filters.append(["warehouse", "=", warehouse])
	if item_group:
		lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])
		# Optimized: Use INNER JOIN instead of EXISTS for better performance
		items = frappe.db.sql_list(
			"""
			SELECT i.name FROM `tabItem` i
			INNER JOIN `tabItem Group` ig ON i.item_group = ig.name
			WHERE ig.lft >= %s AND ig.rgt <= %s
		""",
			(lft, rgt),
		)
		filters.append(["item_code", "in", items])
	try:
		# check if user has any restrictions based on user permissions on warehouse
		if build_match_conditions("Warehouse", user=frappe.session.user):
			filters.append(["warehouse", "in", [w.name for w in frappe.get_list("Warehouse")]])
	except frappe.PermissionError:
		# user does not have access on warehouse
		return []

	items = frappe.db.get_all(
		"Bin",
		fields=[
			"item_code",
			"warehouse",
			"projected_qty",
			"reserved_qty",
			"reserved_qty_for_production",
			"reserved_qty_for_sub_contract",
			"actual_qty",
			"valuation_rate",
		],
		or_filters={
			"projected_qty": ["!=", 0],
			"reserved_qty": ["!=", 0],
			"reserved_qty_for_production": ["!=", 0],
			"reserved_qty_for_sub_contract": ["!=", 0],
			"actual_qty": ["!=", 0],
		},
		filters=filters,
		order_by=sort_by + " " + sort_order,
		limit_start=start,
		limit_page_length=21,
	)

	item_code_list = [item_code] if item_code else [i.item_code for i in items]
	warehouse_list = [warehouse] if warehouse else [i.warehouse for i in items]

	sre_reserved_stock_details = get_reserved_stock_details(item_code_list, warehouse_list)
	# Cache precision to avoid repeated DB calls
	precision = cint(frappe.cache().get_value("float_precision") or 
		frappe.db.get_single_value("System Settings", "float_precision"))

	# Optimized: Fetch all Item details in one query instead of 3-4 queries per row
	if items:
		item_codes = list(set([i.item_code for i in items]))
		item_details = frappe.db.get_all(
			"Item",
			filters={"name": ["in", item_codes]},
			fields=["name", "item_name", "stock_uom", "has_batch_no", "has_serial_no"]
		)
		item_map = {i.name: i for i in item_details}
	else:
		item_map = {}

	for item in items:
		item_info = item_map.get(item.item_code, {})
		item.update(
			{
				"item_code": escape_html(item.item_code),
				"item_name": escape_html(item_info.get("item_name", "")),
				"stock_uom": escape_html(item_info.get("stock_uom", "")),
				"warehouse": escape_html(item.warehouse),
				"disable_quick_entry": item_info.get("has_batch_no") or item_info.get("has_serial_no"),
				"projected_qty": flt(item.projected_qty, precision),
				"reserved_qty": flt(item.reserved_qty, precision),
				"reserved_qty_for_production": flt(item.reserved_qty_for_production, precision),
				"reserved_qty_for_sub_contract": flt(item.reserved_qty_for_sub_contract, precision),
				"actual_qty": flt(item.actual_qty, precision),
				"reserved_stock": flt(sre_reserved_stock_details.get((item.item_code, item.warehouse))),
			}
		)

	return items
