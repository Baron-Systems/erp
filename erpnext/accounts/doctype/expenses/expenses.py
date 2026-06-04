# Copyright (c) 2026, Baron Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

import erpnext
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.accounts.utils import get_account_currency


class expenses(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		amount: DF.Currency
		company: DF.Link
		cost_center: DF.Link | None
		date_expenditure: DF.Date
		description: DF.LongText | None
		mode_of_payment: DF.Link
		name_expense: DF.Link
		naming_series: DF.Literal["ACC-EXP-.YYYY.-"]
	# end: auto-generated types

	def validate(self):
		self.set_missing_values()

	def set_missing_values(self):
		if not self.cost_center and self.company:
			self.cost_center = erpnext.get_default_cost_center(self.company)

	def on_submit(self):
		self.make_gl_entries()

	def before_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry")

	def on_cancel(self):
		self.make_gl_entries(cancel=True)

	def get_expense_account(self):
		"""Get expense account from Name Expense document"""
		if not self.name_expense:
			frappe.throw(_("Name Expense is required"))
		
		name_expense_doc = frappe.get_doc("Name expense", self.name_expense)
		if not name_expense_doc.account:
			frappe.throw(
				_("Account is not set in Name Expense: {0}").format(self.name_expense)
			)
		
		return name_expense_doc.account

	def get_payment_account(self):
		"""Get payment account from Mode of Payment"""
		if not self.mode_of_payment:
			frappe.throw(_("Mode of Payment is required"))
		
		if not self.company:
			frappe.throw(_("Company is required"))
		
		# Get account from Mode of Payment Account child table
		accounts = frappe.get_all(
			"Mode of Payment Account",
			filters={
				"parent": self.mode_of_payment,
				"company": self.company
			},
			fields=["default_account"]
		)
		
		if not accounts or not accounts[0].default_account:
			frappe.throw(
				_("Default Account is not set for Mode of Payment {0} in Company {1}").format(
					self.mode_of_payment, self.company
				)
			)
		
		return accounts[0].default_account

	def build_gl_map(self):
		"""Build GL entries for the expense"""
		gl_entries = []
		
		expense_account = self.get_expense_account()
		payment_account = self.get_payment_account()
		company_currency = erpnext.get_company_currency(self.company)
		
		# 1. Debit Expense Account (Expense is increasing)
		expense_account_currency = get_account_currency(expense_account)
		gl_entries.append(
			self.get_gl_dict(
				{
					"account": expense_account,
					"account_currency": expense_account_currency,
					"against": payment_account,
					"debit": flt(self.amount),
					"debit_in_account_currency": flt(self.amount),
					"credit": 0,
					"credit_in_account_currency": 0,
					"cost_center": self.cost_center,
					"posting_date": self.date_expenditure,
					"remarks": self.description or _("Expense: {0}").format(self.name_expense),
				}
			)
		)
		
		# 2. Credit Payment Account (Cash/Bank is decreasing)
		payment_account_currency = get_account_currency(payment_account)
		gl_entries.append(
			self.get_gl_dict(
				{
					"account": payment_account,
					"account_currency": payment_account_currency,
					"against": expense_account,
					"debit": 0,
					"debit_in_account_currency": 0,
					"credit": flt(self.amount),
					"credit_in_account_currency": flt(self.amount),
					"cost_center": self.cost_center,
					"posting_date": self.date_expenditure,
					"remarks": self.description or _("Expense: {0}").format(self.name_expense),
				}
			)
		)
		
		return gl_entries

	def get_gl_dict(self, args):
		"""Create GL Entry dictionary with common fields"""
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
		from erpnext.accounts.utils import get_fiscal_year
		
		posting_date = args.get("posting_date") or self.date_expenditure
		fiscal_year = get_fiscal_year(posting_date, company=self.company)[0]
		
		gl_dict = frappe._dict(
			{
				"company": self.company,
				"posting_date": posting_date,
				"fiscal_year": fiscal_year,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"remarks": args.get("remarks", ""),
				"debit": args.get("debit", 0),
				"credit": args.get("credit", 0),
				"debit_in_account_currency": args.get("debit_in_account_currency", 0),
				"credit_in_account_currency": args.get("credit_in_account_currency", 0),
				"account": args.get("account"),
				"account_currency": args.get("account_currency"),
				"against": args.get("against"),
				"cost_center": args.get("cost_center"),
				"party_type": None,
				"party": None,
				"is_opening": "No",
			}
		)
		
		# Add accounting dimensions
		accounting_dimensions = get_accounting_dimensions()
		for dimension in accounting_dimensions:
			gl_dict[dimension] = self.get(dimension)
		
		gl_dict.update(args)
		
		return gl_dict

	def make_gl_entries(self, cancel=False):
		"""Create or cancel GL entries"""
		from erpnext.accounts.general_ledger import process_gl_map
		
		gl_entries = self.build_gl_map()
		
		merge_entries = frappe.get_single_value(
			"Accounts Settings", "merge_similar_account_heads"
		)
		
		if cancel:
			make_reverse_gl_entries(
				voucher_type=self.doctype,
				voucher_no=self.name
			)
		else:
			gl_entries = process_gl_map(gl_entries, merge_entries=merge_entries)
			make_gl_entries(gl_entries, cancel=cancel, merge_entries=merge_entries)
