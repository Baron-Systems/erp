# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_data(filters):
	if not filters:
		filters = frappe._dict()

	# Get items with minimum_quantity set
	items = get_items_with_minimum_qty(filters)
	if not items:
		return []

	# Get bin data for these items
	bin_data = get_bin_data(items, filters)

	# Build results
	results = []
	for row in bin_data:
		item = items.get(row.item_code)
		if not item:
			continue

		min_qty = flt(item.minimum_quantity)
		actual_qty = flt(row.actual_qty)

		# Only include if actual qty <= minimum quantity
		if actual_qty <= min_qty:
			results.append({
				"item_code": row.item_code,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"stock_uom": item.stock_uom,
				"warehouse": row.warehouse,
				"actual_qty": actual_qty,
				"minimum_quantity": min_qty,
				"company": row.company,
			})

	return results


def get_items_with_minimum_qty(filters):
	"""Get items that have minimum_quantity > 0"""
	if not filters:
		filters = frappe._dict()

	item = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(item)
		.select(
			item.name,
			item.item_name,
			item.item_group,
			item.stock_uom,
			item.minimum_quantity,
		)
		.where(
			(item.disabled == 0)
			& (item.is_stock_item == 1)
			& (item.minimum_quantity.isnotnull())
			& (item.minimum_quantity > 0)
		)
	)

	if filters.get("item_group"):
		query = query.where(item.item_group == filters.get("item_group"))

	if filters.get("item_code"):
		query = query.where(item.name == filters.get("item_code"))

	items = query.run(as_dict=True)
	return {item.name: item for item in items}


def get_bin_data(items, filters):
	"""Get bin data for given items"""
	if not items:
		return []

	if not filters:
		filters = frappe._dict()

	bin = frappe.qb.DocType("Bin")
	warehouse = frappe.qb.DocType("Warehouse")

	item_codes = list(items.keys())

	query = (
		frappe.qb.from_(bin)
		.join(warehouse)
		.on(bin.warehouse == warehouse.name)
		.select(
			bin.item_code,
			bin.warehouse,
			bin.actual_qty,
			warehouse.company,
		)
		.where(bin.item_code.isin(item_codes))
	)

	if filters.get("company"):
		query = query.where(warehouse.company == filters.get("company"))

	if filters.get("warehouse"):
		query = query.where(bin.warehouse.isin(filters.get("warehouse")))

	return query.run(as_dict=True)


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 150,
		},
		{
			"label": _("UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150,
		},
		{
			"label": _("Current Quantity"),
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"width": 140,
			"convertible": "qty",
		},
		{
			"label": _("Minimum Quantity"),
			"fieldname": "minimum_quantity",
			"fieldtype": "Float",
			"width": 140,
			"convertible": "qty",
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 150,
		},
	]
