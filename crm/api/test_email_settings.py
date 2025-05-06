import frappe
import json
import os

@frappe.whitelist()
def test_email_settings():
    """Test the current email settings and return diagnostic information"""
    result = {
        "system_settings": {},
        "email_accounts": [],
        "resend_config": {},
        "detailed_settings": {}
    }
    
    # Check System Settings
    try:
        email_pref = frappe.db.get_single_value("System Settings", "crm_email_sending_service")
        result["system_settings"]["crm_email_sending_service"] = email_pref
    except Exception as e:
        result["system_settings"]["error"] = str(e)
    
    # List all Email Accounts
    try:
        accounts = frappe.get_all("Email Account", 
                               filters={"enabled": 1},
                               fields=["name", "email_id", "default_outgoing", "smtp_server"])
        result["email_accounts"] = accounts
    except Exception as e:
        result["email_accounts"] = {"error": str(e)}
    
    # Check Resend Configuration
    result["resend_config"] = {
        "RESEND_API_KEY": bool(os.getenv("RESEND_API_KEY")),
        "RESEND_DEFAULT_FROM": os.getenv("RESEND_DEFAULT_FROM"),
        "OPENROUTER_KEY": bool(os.getenv("OPENROUTER_KEY")),
        "SENDER_NAME": os.getenv("SENDER_NAME")
    }
    
    # Check for the detailed settings
    try:
        # Get email settings from Frappe's configuration
        result["detailed_settings"]["outgoing_mail_server"] = frappe.conf.get("mail_server")
        result["detailed_settings"]["outgoing_mail_port"] = frappe.conf.get("mail_port")
        result["detailed_settings"]["use_tls"] = frappe.conf.get("use_tls")
        result["detailed_settings"]["default_outgoing"] = frappe.conf.get("mail_login")
    except Exception as e:
        result["detailed_settings"]["error"] = str(e)
    
    return result

@frappe.whitelist()
def send_test_email_via_system(recipient_email=None):
    """Send a test email using the system's email configuration"""
    if not recipient_email:
        recipient_email = frappe.session.user
    
    try:
        # Get current email preference
        email_pref = frappe.db.get_single_value("System Settings", "crm_email_sending_service") or "resend"
        
        frappe.sendmail(
            recipients=recipient_email,
            subject="Test Email from Frappe CRM",
            message=f"""
            <p>This is a test email from your Frappe CRM system.</p>
            <p>Current email sending service: <strong>{email_pref}</strong></p>
            <p>Timestamp: {frappe.utils.now()}</p>
            """
        )
        
        return {
            "success": True,
            "message": f"Test email sent to {recipient_email} using Frappe's sendmail"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error sending test email: {str(e)}"
        }

@frappe.whitelist()
def set_test_email_preference(preference):
    """Set the email preference for testing"""
    if preference not in ["resend", "frappe"]:
        return {
            "success": False,
            "message": "Invalid preference. Use 'resend' or 'frappe'."
        }
    
    try:
        # Save the setting
        frappe.db.set_value("System Settings", "System Settings", 
                          "crm_email_sending_service", preference)
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Email preference set to {preference} for testing"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error setting test preference: {str(e)}"
        }

@frappe.whitelist()
def debug_email_ui():
    """Debug function to help identify why the toggle isn't appearing"""
    result = {
        "email_systems": {
            "frappe_configured": False,
            "resend_configured": False
        },
        "system_settings": {},
        "email_accounts": [],
        "resend_env": {},
        "ui_should_show_toggle": False,
        "detailed_email_accounts": []
    }
    
    # Check System Settings
    try:
        email_pref = frappe.db.get_single_value("System Settings", "crm_email_sending_service")
        result["system_settings"]["crm_email_sending_service"] = email_pref
    except Exception as e:
        result["system_settings"]["error"] = str(e)
    
    # Check Frappe Email Configuration
    try:
        accounts = frappe.get_all("Email Account", 
                               filters={"enabled": 1, "default_outgoing": 1},
                               fields=["name", "email_id", "default_outgoing", "smtp_server"])
        
        # Get more details about each account
        for account in accounts:
            try:
                doc = frappe.get_doc("Email Account", account.name)
                result["detailed_email_accounts"].append({
                    "name": doc.name,
                    "email_id": doc.email_id,
                    "enabled": doc.enabled,
                    "default_outgoing": doc.default_outgoing,
                    "smtp_server": doc.smtp_server,
                    "smtp_port": doc.smtp_port,
                    "use_tls": doc.use_tls,
                })
            except Exception as e:
                result["detailed_email_accounts"].append({
                    "name": account.name,
                    "error": str(e)
                })
                
        result["email_accounts"] = accounts
        result["email_systems"]["frappe_configured"] = len(accounts) > 0
    except Exception as e:
        result["email_accounts"] = {"error": str(e)}
    
    # Check Resend Configuration
    api_key = os.getenv("RESEND_API_KEY")
    default_from = os.getenv("RESEND_DEFAULT_FROM")
    
    result["resend_env"] = {
        "RESEND_API_KEY": api_key[:5] + "..." + api_key[-4:] if api_key and len(api_key) > 9 else None,
        "RESEND_DEFAULT_FROM": default_from,
        "OPENROUTER_KEY": bool(os.getenv("OPENROUTER_KEY")),
        "SENDER_NAME": os.getenv("SENDER_NAME")
    }
    
    result["email_systems"]["resend_configured"] = bool(api_key) and bool(default_from)
    
    # Check if UI should show toggle
    result["ui_should_show_toggle"] = (
        result["email_systems"]["frappe_configured"] and 
        result["email_systems"]["resend_configured"]
    )
    
    # Force update the System Settings if needed
    if result["email_systems"]["resend_configured"] and not email_pref:
        try:
            frappe.db.set_value("System Settings", "System Settings", 
                             "crm_email_sending_service", "resend")
            frappe.db.commit()
            result["system_settings"]["crm_email_sending_service"] = "resend"
            result["system_settings"]["updated"] = True
        except Exception as e:
            result["system_settings"]["update_error"] = str(e)
    
    return result 