# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class check(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from erpnext.accounts.doctype.installment.installment import installment
		from frappe.types import DF

		check_due_date: DF.Date
		chek_status: DF.Literal["\u0641\u064a \u0627\u0644\u0635\u0646\u062f\u0648\u0642", "\u0645\u062f\u0641\u0648\u0639", "\u0645\u0638\u0647\u0631 \u0644\u0645\u0648\u0631\u062f", "\u0631\u0627\u062c\u0639", "\u0645\u0642\u0633\u0637"]
		chek_value: DF.Currency
		customer: DF.Link | None
		date_of_endorsement: DF.Date | None
		image_check: DF.AttachImage | None
		installment_payment_customer: DF.Table[installment]
		installment_payment_supplier: DF.Table[installment]
		name_check_issuer: DF.Data | None
		naming_series: DF.Literal["ACC-CHK-.YYYY.-"]
		number_check: DF.Int
		payment_voucher: DF.Link | None
		payments_against_invoice: DF.Link | None
		remaining_amount_for_customer: DF.Currency
		remaining_amount_for_supplier: DF.Currency
		supplier: DF.Link | None
	# end: auto-generated types

	def validate(self):
		self.validate_installments_totals()

	def validate_installments_totals(self):
		# حساب مجموع أقساط المورد
		supplier_total = sum(row.installment_amount for row in self.installment_payment_supplier) if self.installment_payment_supplier else 0
		if supplier_total > self.chek_value:
			frappe.throw(_("مجموع أقساط المورد ({0}) يتجاوز قيمة الشيك ({1})").format(supplier_total, self.chek_value))

		# حساب مجموع أقساط العميل
		customer_total = sum(row.installment_amount for row in self.installment_payment_customer) if self.installment_payment_customer else 0
		if customer_total > self.chek_value:
			frappe.throw(_("مجموع أقساط العميل ({0}) يتجاوز قيمة الشيك ({1})").format(customer_total, self.chek_value))

		# تحديث الحقول المتبقية
		self.remaining_amount_for_supplier = self.chek_value - supplier_total
		self.remaining_amount_for_customer = self.chek_value - customer_total