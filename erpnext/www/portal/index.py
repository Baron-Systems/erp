import frappe
from frappe import _

def get_context(context):
    """
    Main dashboard - requires authentication
    """
    # This is handled by JavaScript in the HTML file
    # The token verification happens on the client side
    return context

