import frappe
from frappe.utils import get_request_session, now_datetime
from frappe.utils.response import build_response

@frappe.whitelist(allow_guest=True)
def get_hello_message():
    """
    Simple API endpoint that returns a hello message with the current time
    """
    current_time = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    return {"message": f"Hello from the backend! Current time: {current_time}"}
