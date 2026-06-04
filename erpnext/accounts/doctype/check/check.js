// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// frappe.ui.form.on("check", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on('check', {
    // عند تحميل النموذج أو تغيير قيمة الشيك
    chek_value: function(frm) {
        update_remaining_amounts(frm);
    }
});

// مراقبة التغييرات في جدول أقساط المورد
frappe.ui.form.on('installment', {
    // عند إضافة سطر جديد أو حذف سطر
    installment_payment_supplier_add: function(frm) {
        update_remaining_supplier(frm);
    },
    installment_payment_supplier_remove: function(frm) {
        update_remaining_supplier(frm);
    },
    // عند تغيير قيمة القسط في أي سطر
    value: function(frm, cdt, cdn) {
        update_remaining_supplier(frm);
    }
});

// مراقبة التغييرات في جدول أقساط العميل
frappe.ui.form.on('installment', {
    installment_payment_customer_add: function(frm) {
        update_remaining_customer(frm);
    },
    installment_payment_customer_remove: function(frm) {
        update_remaining_customer(frm);
    },
    value: function(frm, cdt, cdn) {
        // تحديد الجدول الذي ينتمي إليه السطر
        let row = locals[cdt][cdn];
        if (row.parentfield === 'installment_payment_customer') {
            update_remaining_customer(frm);
        }
    }
});

// دالة حساب المتبقي للمورد
function update_remaining_supplier(frm) {
    let total = 0;
    $.each(frm.doc.installment_payment_supplier || [], function(i, row) {
        total += flt(row.value);  // value هو حقل قيمة القسط
    });
    let remaining = flt(frm.doc.chek_value) - total;
    frm.set_value('remaining_amount_for_supplier', remaining > 0 ? remaining : 0);
}

// دالة حساب المتبقي للعميل
function update_remaining_customer(frm) {
    let total = 0;
    $.each(frm.doc.installment_payment_customer || [], function(i, row) {
        total += flt(row.value);
    });
    let remaining = flt(frm.doc.chek_value) - total;
    frm.set_value('remaining_amount_for_customer', remaining > 0 ? remaining : 0);
}

// دالة شاملة تحديث كلا المتبقيين (تُستدعى عند تغيير chek_value)
function update_remaining_amounts(frm) {
    update_remaining_supplier(frm);
    update_remaining_customer(frm);
}