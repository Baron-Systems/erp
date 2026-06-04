import frappe
import jwt
import hashlib
import hmac
from datetime import datetime, timedelta
from frappe import _
from frappe.utils import flt
import json
import re
from frappe.auth import CookieManager

# Secret key for JWT (should be stored securely)
def get_secret_key():
    """Get or create a *stable* secret key for JWT signing.

    - Prefer site_config.json (frappe.conf)
    - If missing, write once to site_config.json so tokens remain valid across restarts
    """
    secret = frappe.conf.get("customer_portal_secret")
    if secret:
        return secret

    # Try cache (per process)
    try:
        cached = frappe.cache().get_value("customer_portal_secret")
        if cached:
            return cached
    except Exception:
        pass

    # Read/write site_config.json
    try:
        site_config_path = frappe.get_site_path("site_config.json")
        data = {}
        try:
            with open(site_config_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}

        secret = data.get("customer_portal_secret")
        if not secret:
            secret = frappe.generate_hash(length=64)
            data["customer_portal_secret"] = secret
            with open(site_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

        try:
            frappe.cache().set_value("customer_portal_secret", secret)
        except Exception:
            pass

        return secret
    except Exception:
        # Last resort (won't persist across restarts)
        secret = frappe.generate_hash(length=64)
        try:
            frappe.cache().set_value("customer_portal_secret", secret)
        except Exception:
            pass
        return secret


_AR_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize_ar(text: str) -> str:
    """Normalize Arabic text for tolerant matching (no diacritics, common letter  variants)."""
    if not text:
        return ""
    s = str(text).strip().lower()
    s = s.replace("ـ", "")  # tatweel
    s = _AR_DIACRITICS_RE.sub("", s)
    # Normalize common Arabic letter variants
    s = re.sub(r"[إأآٱ]", "ا", s)
    s = s.replace("ى", "ي")
    s = s.replace("ؤ", "و").replace("ئ", "ي")
    # Keep ة as-is (people may type it); but also normalize extra spaces
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_id_no(text: str) -> str:
    """Normalize ID by removing spaces/dashes/underscores/slashes."""
    if not text:
        return ""
    s = str(text).strip()
    return re.sub(r"[\s\-_\/]+", "", s)


def set_customer_token_cookie(token: str):
    """Set secure HttpOnly cookie for portal token."""
    # Use Frappe's CookieManager (compatible with Frappe versions / request lifecycle)
    if not hasattr(frappe.local, "cookie_manager"):
        # Should exist for normal HTTP requests, but keep a safe fallback
        frappe.local.cookie_manager = CookieManager()

    frappe.local.cookie_manager.set_cookie(
        "customer_token",
        token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=30 * 60,
    )


@frappe.whitelist(allow_guest=True)
def portal_me():
    """Return customer info if token cookie is valid (used by frontend auth checks)."""
    customer_id = get_customer_from_request()
    if not customer_id:
        return {"success": False}

    if not frappe.db.exists("Customer", customer_id):
        return {"success": False}

    customer_name = frappe.db.get_value("Customer", customer_id, "customer_name")
    id_no = frappe.db.get_value("Customer", customer_id, "id_no")
    return {
        "success": True,
        "customer": {"customer_id": customer_id, "customer_name": customer_name, "id_no": id_no},
    }


@frappe.whitelist(allow_guest=True)
def portal_logout():
    """Logout from portal by deleting the HttpOnly token cookie."""
    try:
        if hasattr(frappe.local, "cookie_manager"):
            frappe.local.cookie_manager.delete_cookie("customer_token")
        return {"success": True}
    except Exception:
        return {"success": True}

def get_default_currency():
    """Get default company currency"""
    try:
        # Get default company
        default_company = frappe.db.get_single_value("Global Defaults", "default_company")
        if default_company:
            currency = frappe.db.get_value("Company", default_company, "default_currency")
            if currency:
                return currency
        
        # Fallback to SAR if no company found
        return "SAR"
    except:
        return "SAR"


def _get_item_portal_fieldnames():
    """Return (publish_field, show_price_field) actually present on Item.
    
    Now only checks for publish field, show_price is removed.
    """
    meta = frappe.get_meta("Item")
    publish_field = None

    # Preferred custom fieldnames (per requirement)
    if meta.has_field("publish"):
        publish_field = "publish"
    elif meta.has_field("published_in_website"):
        publish_field = "published_in_website"
    elif meta.has_field("show_in_website"):
        publish_field = "show_in_website"

    # show_price field is no longer used - always return None
    return publish_field, None


def _get_price_lists():
    """Get price lists from Selling Settings for portal.
    
    Returns:
        tuple: (selling_price_list, offer_price_list)
    """
    try:
        # Get Selling Settings
        selling_settings = frappe.get_doc("Selling Settings")
        
        # Get the configured price lists
        selling_price_list = selling_settings.get("selling_price_list")
        offer_price_list = selling_settings.get("offer_price_list")
        
        return selling_price_list, offer_price_list
    except Exception as e:
        frappe.log_error(f"Error getting price lists from Selling Settings: {str(e)}")
        return None, None


def _detect_item_price_list_fields():
    """DEPRECATED: Now uses Selling Settings instead of per-item fields.
    
    Returns None for both fields as we now use global Selling Settings.
    """
    return None, None


def _resolve_item_price_lists(item_dict: dict):
    """Return (standard_pl, offers_pl, standard_field, offers_field) from Selling Settings.
    
    Now uses global Selling Settings instead of per-item fields.
    """
    # Get price lists from Selling Settings
    standard_pl, offers_pl = _get_price_lists()
    
    # Return None for fields since we don't use per-item fields anymore
    return standard_pl, offers_pl, None, None


@frappe.whitelist(allow_guest=True)
def get_portal_settings():
    """Return portal settings needed by frontend (currency + price lists from Selling Settings)."""
    currency = get_default_currency()
    standard_pl, offers_pl = _get_price_lists()
    return {
        "success": True,
        "currency": currency,
        "item_price_list_fields": {"standard": standard_pl, "offers": offers_pl},
    }


@frappe.whitelist(allow_guest=True)
def portal_get_csrf_token():
    """Return a CSRF token for the current session (works for Guest too).

    Some setups block calling `frappe.sessions.get_csrf_token` for Guest (403).
    This endpoint provides a safe fallback for our standalone portal pages.
    """
    try:
        # First, try to get from session data directly (safest for guest)
        session = getattr(frappe, "local", None) and getattr(frappe.local, "session", None)
        if session:
            token = getattr(session, "data", {}).get("csrf_token")
            if token:
                return token

        # Second, try frappe.sessions.get_csrf_token
        try:
            from frappe.sessions import get_csrf_token as _get_csrf_token
            token = _get_csrf_token()
            if token:
                return token
        except Exception:
            pass

        # Third, try to generate a new token if we have session
        try:
            if session and hasattr(session, 'data'):
                from frappe.utils import generate_hash
                token = generate_hash(10)
                session.data.csrf_token = token
                return token
        except Exception:
            pass

        return ""
    except Exception as e:
        frappe.log_error(f"portal_get_csrf_token error: {str(e)}")
        return ""


@frappe.whitelist(allow_guest=True)
def verify_customer(id_no, customer_name):
    """
    Verify customer using ID NO and Customer Name
    Returns JWT token if verification is successful
    """
    try:
        # Ensure required field exists
        meta = frappe.get_meta("Customer")
        if not meta.has_field("id_no"):
            return {
                "success": False,
                "message": "حقل رقم الهوية (id_no) غير موجود في Customer. الرجاء تشغيل إعداد الحقول أو إضافته يدويًا.",
            }

        # Clean and normalize inputs
        id_no_raw = str(id_no or "").strip()
        name_raw = str(customer_name or "").strip()

        id_no_clean = normalize_id_no(id_no_raw)
        name_clean = normalize_ar(name_raw)

        if not id_no_clean or not name_clean:
            return {"success": False, "message": "الرجاء إدخال رقم الهوية والاسم الأول"}
        
        # Find customer by ID NO (tolerant: ignore spaces/dashes in stored value)
        customer_rows = frappe.db.sql(
            """
            SELECT name, customer_name, id_no
            FROM `tabCustomer`
            WHERE REPLACE(REPLACE(REPLACE(IFNULL(id_no,''), ' ', ''), '-', ''), '_', '') = %s
            LIMIT 1
            """,
            (id_no_clean,),
            as_dict=True,
        )
        customer = customer_rows[0] if customer_rows else None
        
        if not customer:
            return {
                "success": False,
                "message": "لم يتم العثور على عميل بهذا المعرف"
            }
        
        # Check if customer name matches (first name is enough)
        stored_name = normalize_ar(customer.customer_name)
        
        # Check if input matches the beginning of the stored name
        if not stored_name.startswith(name_clean):
            return {
                "success": False,
                "message": "الاسم غير متطابق (يكفي إدخال الاسم الأول كما هو مسجل)"
            }
        
        # Generate JWT token + set HttpOnly cookie
        token = generate_customer_token(customer.name, customer.customer_name)
        set_customer_token_cookie(token)

        return {
            "success": True,
            "customer_name": customer.customer_name
        }
        
    except Exception as e:
        frappe.log_error(f"Customer Verification Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء التحقق"
        }

def generate_customer_token(customer_id, customer_name):
    """Generate JWT token for customer"""
    secret = get_secret_key()
    
    payload = {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "issued_at": datetime.now().isoformat(),
        "expiry": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

def verify_token(token):
    """Verify and decode JWT token"""
    try:
        secret = get_secret_key()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        
        # Check expiry
        expiry = datetime.fromisoformat(payload["expiry"])
        if datetime.now() > expiry:
            return None
        
        return payload
    except:
        return None

def get_customer_from_request():
    """Get customer from request token (cookie or header)"""
    # Try to get token from cookie
    token = frappe.request.cookies.get("customer_token")
    
    # Try to get token from Authorization header
    if not token:
        auth_header = frappe.get_request_header("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        return None
    
    payload = verify_token(token)
    if not payload:
        return None
    
    return payload.get("customer_id")

def check_customer_permission(doctype, doc_name):
    """Check if current customer has permission to access document"""
    customer_id = get_customer_from_request()
    
    if not customer_id:
        frappe.throw(_("غير مصرح لك بالوصول"), frappe.PermissionError)
    
    # Get document and check if it belongs to customer
    doc = frappe.get_doc(doctype, doc_name)
    
    if doc.customer != customer_id:
        frappe.throw(_("غير مصرح لك بالوصول لهذا المستند"), frappe.PermissionError)
    
    return True



def get_item_price_info(item_code, standard_pl=None, offers_pl=None):
    """Get price information for an item"""
    try:
        # STRICT: portal prices come only from Item-provided price lists
        if not standard_pl:
            return {
                "standard_price": 0,
                "offer_price": 0,
                "has_offer": False,
                "discount_percent": 0,
            }

        # Get standard price
        standard_price = frappe.db.get_value("Item Price", {
            "item_code": item_code,
            "price_list": standard_pl
        }, "price_list_rate") or 0
        
        # Get offer price
        offer_price = 0
        if offers_pl and frappe.db.exists("Price List", offers_pl):
            offer_price = frappe.db.get_value("Item Price", {
                "item_code": item_code,
                "price_list": offers_pl
            }, "price_list_rate") or 0
        
        # If no standard price, try to get from item
        if not standard_price:
            standard_price = frappe.db.get_value("Item", item_code, "standard_rate") or 0
        
        return {
            "standard_price": float(standard_price),
            "offer_price": float(offer_price),
            "has_offer": bool(offer_price and offer_price > 0),
            "discount_percent": round((1 - (offer_price / standard_price)) * 100) if (standard_price and offer_price) else 0
        }
    except Exception as e:
        frappe.log_error(f"Get Item Price Info Error for {item_code}: {str(e)}")
        return {
            "standard_price": 0,
            "offer_price": 0,
            "has_offer": False,
            "discount_percent": 0
        }

@frappe.whitelist(allow_guest=True)
def get_item_groups():
    """Get all item groups for filtering"""
    try:
        groups = frappe.get_all(
            "Item Group",
            filters={"is_group": 0},
            fields=["name", "item_group_name"],
            order_by="name"
        )
        
        return {
            "success": True,
            "groups": groups
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب المجموعات"
        }

# ============== Customer Dashboard API ==============

@frappe.whitelist(allow_guest=True)
def get_dashboard_data():
    """Get customer dashboard data"""
    customer_id = get_customer_from_request()
    
    if not customer_id:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول"
        }
    
    try:
        # Get customer details
        customer = frappe.get_doc("Customer", customer_id)
        
        # Get account balance
        balance = get_customer_balance(customer_id)
        
        # Get recent invoices
        recent_invoices = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer_id, "docstatus": 1},
            fields=["name", "posting_date", "grand_total", "outstanding_amount", "status"],
            order_by="posting_date desc",
            limit=5
        )
        
        # Get recent orders - all orders without limit
        recent_orders = frappe.get_all(
            "Sales Order",
            filters={"customer": customer_id},
            fields=["name", "transaction_date", "grand_total", "status"],
            order_by="transaction_date desc"
        )
        
        return {
            "success": True,
            "customer": {
                "name": customer.customer_name,
                "id_no": customer.id_no,
                "customer_id": customer_id
            },
            "balance": balance,
            "recent_invoices": recent_invoices,
            "recent_orders": recent_orders
        }
        
    except Exception as e:
        frappe.log_error(f"Dashboard Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب البيانات"
        }

def get_customer_balance(customer_id):
    """Get customer account balance including opening balance from GL Entries"""
    from erpnext.accounts.utils import get_balance_on
    from erpnext.accounts.party import get_party_account
    
    try:
        # Get customer's receivable account (with fallback to company default)
        receivable_account = None
        try:
            receivable_account = get_party_account("Customer", customer_id, None)
        except Exception:
            # If no company specified, try to get from customer doc
            customer = frappe.get_doc("Customer", customer_id)
            if customer.accounts:
                receivable_account = customer.accounts[0].account
        
        # Get balance from GL Entries - this INCLUDES opening entries automatically
        # Opening entries are GL Entries with is_opening="Yes" or posting_date in previous fiscal year
        gl_balance = 0
        if receivable_account:
            gl_balance = get_balance_on(
                account=receivable_account, 
                party_type="Customer", 
                party=customer_id
            )
        else:
            # Fallback: get balance by party only (without specific account)
            gl_balance = get_balance_on(
                party_type="Customer", 
                party=customer_id
            )
        
        # Debug logging
        frappe.log_error(f"Balance for {customer_id}: Account={receivable_account}, Balance={gl_balance}")
        
        return gl_balance
        
    except Exception as e:
        frappe.log_error(f"Balance Error for {customer_id}: {str(e)}")
        return 0

# ============== Invoices API ==============

@frappe.whitelist(allow_guest=True)
def get_invoices(status=None, from_date=None, to_date=None):
    """Get customer invoices with filters"""
    customer_id = get_customer_from_request()
    
    if not customer_id:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول"
        }
    
    try:
        filters = {"customer": customer_id, "docstatus": 1}
        
        if status:
            filters["status"] = status
        
        if from_date:
            filters["posting_date"] = [">=", from_date]
        
        if to_date:
            if "posting_date" in filters:
                filters["posting_date"] = ["between", [from_date, to_date]]
            else:
                filters["posting_date"] = ["<=", to_date]
        
        invoices = frappe.get_all(
            "Sales Invoice",
            filters=filters,
            fields=[
                "name", "posting_date", "due_date", "grand_total",
                "outstanding_amount", "status", "currency"
            ],
            order_by="posting_date desc"
        )
        
        # Format dates to numbers only (YYYY-MM-DD)
        formatted_invoices = []
        for inv in invoices:
            formatted_inv = inv.copy()
            if hasattr(inv.posting_date, 'strftime'):
                formatted_inv['posting_date'] = inv.posting_date.strftime('%Y-%m-%d')
            else:
                formatted_inv['posting_date'] = str(inv.posting_date)
            
            if hasattr(inv.due_date, 'strftime'):
                formatted_inv['due_date'] = inv.due_date.strftime('%Y-%m-%d')
            else:
                formatted_inv['due_date'] = str(inv.due_date)
            
            formatted_invoices.append(formatted_inv)
        
        return {
            "success": True,
            "invoices": formatted_invoices
        }
        
    except Exception as e:
        frappe.log_error(f"Get Invoices Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب الفواتير"
        }

@frappe.whitelist(allow_guest=True)
def get_invoice_details(invoice_name):
    """Get single invoice details"""
    customer_id = get_customer_from_request()
    
    if not customer_id:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول"
        }
    
    try:
        # Check permission
        check_customer_permission("Sales Invoice", invoice_name)
        
        # Get invoice
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        
        items = []
        for item in invoice.items:
            items.append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate,
                "amount": item.amount
            })
        
        return {
            "success": True,
            "invoice": {
                "name": invoice.name,
                "customer_name": invoice.customer_name,
                "posting_date": invoice.posting_date.strftime('%Y-%m-%d') if hasattr(invoice.posting_date, 'strftime') else str(invoice.posting_date),
                "due_date": invoice.due_date.strftime('%Y-%m-%d') if hasattr(invoice.due_date, 'strftime') else str(invoice.due_date),
                "grand_total": invoice.grand_total,
                "outstanding_amount": invoice.outstanding_amount,
                "status": invoice.status,
                "currency": invoice.currency,
                "items": items
            }
        }
        
    except frappe.PermissionError:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول لهذه الفاتورة"
        }
    except Exception as e:
        frappe.log_error(f"Get Invoice Details Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب تفاصيل الفاتورة"
        }


# ============== Account API ==============

@frappe.whitelist(allow_guest=True)
def get_account_statement(from_date=None, to_date=None):
    """Get customer account statement"""
    customer_id = get_customer_from_request()
    
    if not customer_id:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول"
        }
    
    try:
        # Get customer balance
        balance = get_customer_balance(customer_id)
        
        # Get payment entries
        filters = {"party": customer_id, "party_type": "Customer", "docstatus": 1}
        
        if from_date:
            filters["posting_date"] = [">=", from_date]
        
        if to_date:
            if "posting_date" in filters:
                filters["posting_date"] = ["between", [from_date, to_date]]
            else:
                filters["posting_date"] = ["<=", to_date]
        
        payments = frappe.get_all(
            "Payment Entry",
            filters=filters,
            fields=[
                "name", "posting_date", "paid_amount",
                "payment_type", "mode_of_payment", "reference_no"
            ],
            order_by="posting_date desc",
            limit=50
        )
        
        # Format dates to numbers only (YYYY-MM-DD)
        formatted_payments = []
        for pay in payments:
            formatted_pay = pay.copy()
            if hasattr(pay.posting_date, 'strftime'):
                formatted_pay['posting_date'] = pay.posting_date.strftime('%Y-%m-%d')
            else:
                formatted_pay['posting_date'] = str(pay.posting_date)
            formatted_payments.append(formatted_pay)
        
        return {
            "success": True,
            "balance": balance,
            "payments": formatted_payments
        }
        
    except Exception as e:
        frappe.log_error(f"Get Account Statement Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب كشف الحساب"
        }


@frappe.whitelist(allow_guest=True)
def get_manifest():
    """Generate dynamic PWA manifest based on current domain"""
    try:
        # Get current host from request
        host = frappe.request.host or frappe.request.headers.get('Host', 'localhost')
        
        # Extract subdomain (first part of domain)
        # e.g., market.albaronsystems.com -> market
        domain_parts = host.split('.')
        if len(domain_parts) >= 2 and domain_parts[0] not in ['www', 'portal', 'app']:
            app_name = domain_parts[0].capitalize()
        else:
            app_name = "Portal"
        
        # Get site name for icons
        site_name = frappe.local.site
        
        manifest = {
            "name": f"{app_name}",
            "short_name": f"{app_name}",
            "description": f"بوابة عملاء {app_name} - متابعة الطلبات والفواتير والمنتجات",
            "start_url": "/portal",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#1e3a8a",
            "orientation": "portrait",
            "scope": "/portal/",
            "lang": "ar",
            "dir": "rtl",
            "icons": [
                {
                    "src": "/assets/erpnext/images/erpnext-logo.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable"
                },
                {
                    "src": "/assets/erpnext/images/erpnext-logo.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable"
                }
            ],
            "categories": ["business", "finance"],
            "screenshots": [
                {
                    "src": "/assets/erpnext/images/erpnext-logo.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "form_factor": "narrow",
                    "label": f"بوابة {app_name}"
                }
            ]
        }
        
        # Return as JSON response
        frappe.response['content_type'] = 'application/json'
        return manifest
        
    except Exception as e:
        frappe.log_error(f"Manifest Generation Error: {str(e)}")
        # Fallback to static manifest
        return {
            "name": "Portal",
            "short_name": "Portal",
            "description": "بوابة العملاء",
            "start_url": "/portal",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#1e3a8a",
            "scope": "/portal/",
            "icons": [
                {
                    "src": "/assets/erpnext/images/erpnext-logo.png",
                    "sizes": "192x192",
                    "type": "image/png"
                }
            ]
        }


# ============== Financial Dashboard API ==============

@frappe.whitelist(allow_guest=True)
def get_financial_dashboard(from_date=None, to_date=None, transaction_type=None, invoice_status=None):
    """Get comprehensive financial dashboard for customer"""
    customer_id = get_customer_from_request()

    if not customer_id:
        frappe.log_error("Financial Dashboard: No customer_id found in request. Cookies: " + str(dict(frappe.request.cookies) if frappe.request else "no request"))
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول - يرجى تسجيل الدخول مرة أخرى"
        }

    try:
        frappe.log_error(f"Financial Dashboard: Processing for customer {customer_id}, filters: from={from_date}, to={to_date}, type={transaction_type}, status={invoice_status}")
        
        # Get actual balance from General Ledger (GL Entries) - Net Balance
        # This is the REAL accounting balance from the customer's ledger
        gl_balance = get_customer_balance(customer_id)
        
        frappe.log_error(f"Dashboard GL Balance for {customer_id}: gl_balance={gl_balance}")
        
        # Get invoices with filters
        invoice_filters = {"customer": customer_id, "docstatus": 1}
        if from_date:
            invoice_filters["posting_date"] = [">=", from_date]
        if to_date:
            if "posting_date" in invoice_filters:
                invoice_filters["posting_date"] = ["between", [from_date, to_date]]
            else:
                invoice_filters["posting_date"] = ["<=", to_date]
        if invoice_status:
            invoice_filters["status"] = invoice_status
        
        invoices = frappe.get_all(
            "Sales Invoice",
            filters=invoice_filters,
            fields=["name", "posting_date", "grand_total", "outstanding_amount", "status", "customer", "currency"],
            order_by="posting_date desc"
        )
        
        # Get payments with filters
        payment_filters = {"party": customer_id, "docstatus": 1, "payment_type": "Receive"}
        if from_date:
            payment_filters["posting_date"] = [">=", from_date]
        if to_date:
            if "posting_date" in payment_filters:
                payment_filters["posting_date"] = ["between", [from_date, to_date]]
            else:
                payment_filters["posting_date"] = ["<=", to_date]
        
        payments = frappe.get_all(
            "Payment Entry",
            filters=payment_filters,
            fields=["name", "posting_date", "paid_amount", "status"],
            order_by="posting_date desc"
        )
        
        # Calculate totals
        total_invoices = sum([flt(inv.grand_total) for inv in invoices])
        total_payments = sum([flt(pay.paid_amount) for pay in payments])
        outstanding_invoices = sum([flt(inv.outstanding_amount) for inv in invoices if inv.status != "Paid"])
        paid_invoices = sum([flt(inv.grand_total) for inv in invoices if inv.status == "Paid"])
        
        # Build transactions list
        transactions = []
        
        # Add invoices to transactions
        for inv in invoices:
            if transaction_type and transaction_type != "invoice":
                continue
            
            # Format date to numbers only (YYYY-MM-DD)
            formatted_date = inv.posting_date.strftime('%Y-%m-%d') if hasattr(inv.posting_date, 'strftime') else str(inv.posting_date)
            
            transactions.append({
                "date": formatted_date,
                "type": "invoice",
                "description": f"فاتورة مبيعات #{inv.name}",
                "amount": flt(inv.grand_total),
                "status": inv.status,
                "outstanding": flt(inv.outstanding_amount),
                "currency": inv.currency or get_default_currency()
            })
        
        # Add payments to transactions
        for pay in payments:
            if transaction_type and transaction_type != "payment":
                continue
            
            # Format date to numbers only (YYYY-MM-DD)
            formatted_date = pay.posting_date.strftime('%Y-%m-%d') if hasattr(pay.posting_date, 'strftime') else str(pay.posting_date)
            
            transactions.append({
                "date": formatted_date,
                "type": "payment",
                "description": f"دفع #{pay.name}",
                "amount": flt(pay.paid_amount),
                "status": pay.status,
                "outstanding": 0,
                "currency": get_default_currency()
            })
        
        # Sort transactions by date
        transactions.sort(key=lambda x: x["date"], reverse=True)
        
        # Get default currency
        currency = get_default_currency()
        
        # Count invoices and payments after transaction_type filter
        filtered_invoices = [t for t in transactions if t["type"] == "invoice"]
        filtered_payments = [t for t in transactions if t["type"] == "payment"]
        
        result = {
            "success": True,
            "balance": flt(gl_balance),  # Net balance from General Ledger (GL)
            "invoices_count": len(filtered_invoices),  # Count after filters
            "payments_count": len(filtered_payments),  # Count after filters
            "total_invoice_amount": total_invoices,  # Total amount of invoices
            "total_payment_amount": total_payments,  # Total amount of payments
            "outstanding_invoices": outstanding_invoices,
            "paid_invoices": paid_invoices,
            "transactions": transactions,
            "currency": currency
        }
        
        frappe.log_error(f"Financial Dashboard: Successfully processed for customer {customer_id}")
        return result
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        frappe.log_error(f"Financial Dashboard Error for customer {customer_id}: {str(e)}\n{error_details}")
        return {
            "success": False,
            "message": f"حدث خطأ أثناء جلب البيانات المالية: {str(e)}"
        }


@frappe.whitelist(allow_guest=True)


@frappe.whitelist(allow_guest=True)
def get_customer_balance_endpoint():
    """Get customer current balance and credit information (API endpoint).
    
    This is an endpoint wrapper that calls get_customer_balance(customer_id).
    """
    customer_id = get_customer_from_request()
    
    if not customer_id:
        return {
            "success": False,
            "message": "غير مصرح لك بالوصول"
        }
    
    try:
        try:
            credit_limit = flt(frappe.db.get_value("Customer", customer_id, "credit_limit") or 0)
        except:
            credit_limit = 100000  # Default credit limit if field doesn't exist
        
        try:
            outstanding_amount = flt(frappe.db.get_value("Customer", customer_id, "outstanding_amount") or 0)
        except:
            outstanding_amount = 0  # Default outstanding amount
        
        # Get default currency
        currency = get_default_currency()
        
        return {
            "success": True,
            "balance": credit_limit - outstanding_amount,
            "credit_limit": credit_limit,
            "outstanding_amount": outstanding_amount,
            "currency": currency
        }
        
    except Exception as e:
        frappe.log_error(f"Customer Balance Error: {str(e)}")
        return {
            "success": False,
            "message": "حدث خطأ أثناء جلب رصيد العميل"
        }

