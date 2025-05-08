import frappe
import json
import logging
import os
from frappe import _
from frappe.utils import now_datetime, get_formatted_email
import requests
from frappe.utils.background_jobs import enqueue
import dotenv
from openai import OpenAI
import resend
from pathlib import Path
import datetime
import time

# Try different imports for html2text function
try:
    from frappe.utils.html_utils import html2text
except ImportError:
    try:
        from frappe.utils.html import html2text
    except ImportError:
        # Create a basic fallback function if both imports fail
        def html2text(html_content):
            """Simple fallback to strip HTML tags if the proper function isn't available"""
            import re
            # Remove HTML tags
            text = re.sub(r'<[^>]*>', ' ', html_content)
            # Fix spacing
            text = re.sub(r'\s+', ' ', text).strip()
            return text

# Custom JSON encoder to handle datetime objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        return super().default(obj)

# Set up logging to file (independently of frappe.log)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Safely load environment variables without using frappe.log at module level
def init_environment():
    """Initialize environment variables and logging safely"""
    # Define env path
    env_path = Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

    # Add file handler if not already present
    if not logger.handlers:
        try:
            # Try to get bench path safely
            # Corrected path: Go up 4 levels from __file__ (api/crm/crm/apps) to get to frappe-bench
            bench_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
            log_dir = os.path.join(bench_path, "logs")
            
            # Ensure logs directory exists
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            log_file = os.path.join(log_dir, "ai_email.log")
            print(f"DEBUG: Logger attempting to write to: {log_file}") # Add debug print
            
            file_handler = logging.FileHandler(log_file)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info("AI Email logger initialized")
        except Exception as e:
            # Can't use frappe.log here
            print(f"Error initializing AI Email logger: {str(e)}")
            print(f"Attempted log path: {log_file if 'log_file' in locals() else 'Not determined'}")
            
    # Manually load environment variables from .env file
    try:
        if env_path.exists():
            logger.info(f"Loading .env from {env_path}")
            dotenv.load_dotenv(env_path)
            
            # Check if the keys were loaded
            openrouter_key = os.environ.get("OPENROUTER_KEY")
            if openrouter_key:
                masked_key = f"{openrouter_key[:5]}...{openrouter_key[-4:]}"
                logger.info(f"OPENROUTER_KEY loaded successfully: {masked_key}")
            else:
                logger.warning("OPENROUTER_KEY not found in environment")
    except Exception as e:
        logger.error(f"Error loading .env file: {str(e)}")

# Call the initialization function when needed, not at module level
# init_environment will be called in the appropriate functions

def log(message, level="info"):
    """Custom logging function to ensure all logs go to both the log file and console"""
    # Call init_environment if needed
    if not logger.handlers:
        init_environment()
        
    if level == "debug":
        logger.debug(message)
        # Only use frappe.log if in a valid context
        try:
            frappe.log("AI Email: " + message)
        except Exception:
            pass # Ignore errors if frappe.log is not available (e.g., background job)
    elif level == "info":
        logger.info(message)
        try:
            frappe.log("AI Email: " + message)
        except Exception:
            pass
    elif level == "warning":
        logger.warning(message)
        try:
            frappe.log("AI Email: " + message)
        except Exception:
            pass
    elif level == "error":
        logger.error(message)
        try:
            frappe.log("AI Email: " + message)
        except Exception:
            pass
    else:
        logger.info(message)
        try:
            frappe.log("AI Email: " + message)
        except Exception:
            pass

@frappe.whitelist()
def generate_email_content(lead_name, tone="professional", additional_context=""):
    """Generate email content for a lead using AI, based on V3 prompt logic."""
    init_environment()
    log(f"AI_PROMPT_V3_FLOW: generate_email_content - START for lead: {lead_name}, tone: {tone}", "info")
    
    try:
        lead = frappe.get_doc("CRM Lead", lead_name)
        log(f"AI_PROMPT_V3_FLOW: Lead data retrieved for: {lead.name}", "debug")
        
        lead_fields_dict = lead.as_dict()
        
        openrouter_key = os.getenv("OPENROUTER_KEY")
        if not openrouter_key:
            log("AI_PROMPT_V3_FLOW: OpenRouter API key not found in .env file", "error")
            frappe.throw(_("OpenRouter API key not configured. Please add it to .env file."), title="Configuration Error")
        
        log(f"AI_PROMPT_V3_FLOW: Calling construct_prompt (V3) for lead: {lead.name}", "debug")
        # Pass lead_fields_dict, and the UI-selected tone and additional_context
        prompt_string_to_send, model_identifier_to_use = construct_prompt(
            lead_fields_dict, 
            ui_tone_preference=tone, 
            ui_additional_context=additional_context
        )
        log(f"AI_PROMPT_V3_FLOW: Received from construct_prompt - Model: '{model_identifier_to_use}'. Prompt (first 100 chars): {prompt_string_to_send[:100]}...", "debug")
        
        log(f"AI_PROMPT_V3_FLOW: Calling OpenRouter API for lead: {lead.name}", "debug")
        response = call_openrouter_api(prompt_string_to_send, openrouter_key, model_identifier_to_use)
        log(f"AI_PROMPT_V3_FLOW: Received response from OpenRouter API for lead: {lead.name}. Success: {response.get('success')}", "debug")
        
        if not response["success"]:
            return response
        
        log(f"AI_PROMPT_V3_FLOW: Returning generated content to frontend for lead: {lead.name}", "info")
        return {
            "success": True,
            "subject": response["subject"],
            "content": response["content"],
            "debug_info": {
                "lead_name": lead.lead_name,
                "tone_preference_from_ui": tone, # Reflect what UI sent
                "model_used": model_identifier_to_use or "openai/gpt-4o" # Default if none from DB
            }
        }
        
    except frappe.DoesNotExistError as e:
        log(f"AI_PROMPT_V3_FLOW: Error - Lead '{lead_name}' not found: {str(e)}", "error")
        frappe.throw(_("Lead '{0}' not found.").format(lead_name), title="Not Found")
    except Exception as e:
        log(f"AI_PROMPT_V3_FLOW: Error in generate_email_content for lead {lead_name}: {str(e)}", "error")
        log(f"AI_PROMPT_V3_FLOW: Traceback: {frappe.get_traceback()}", "error")
        if not frappe.exc_already_raised:
             frappe.throw(_("Error generating email content: {0}").format(str(e)), title="Generation Error")
        return { 
            "success": False,
            "message": f"Error generating email: {str(e)}"
        }

def construct_prompt(lead_fields_dict, ui_tone_preference, ui_additional_context):
    """ (V3 Logic)
    Constructs the AI prompt by:
    1. Fetching master instructions from the default CRM AI System Prompt.
    2. Preparing a detailed block of ONLY lead-specific data.
    3. Allowing the master instructions (as a Jinja template) to embed this lead data and UI preferences.
    4. If lead data isn't embedded by the template, it's appended separately.
    5. Appending a standard JSON output format instruction.
    """
    log(f"AI_PROMPT_V3_FLOW: construct_prompt (V3) - START. UI Tone: '{ui_tone_preference}'", "info")

    # 1. Fetch Base Prompt (Master Instructions) & Model ID from CRM AI System Prompt (default)
    default_prompt_settings = frappe.db.get_value(
        "CRM AI System Prompt", 
        {"is_default": 1},
        ["name", "prompt_content", "model_identifier"], 
        as_dict=True
    )

    if not default_prompt_settings:
        log("AI_PROMPT_V3_FLOW: No default CRM AI System Prompt found.", "error")
        frappe.throw(_("Default AI System Prompt not configured. Please set one."), title="Configuration Error")
        return None, None # Defensive return after throw
    
    db_prompt_name = default_prompt_settings.get("name")
    db_master_prompt_instructions = default_prompt_settings.get("prompt_content")
    db_model_identifier = default_prompt_settings.get("model_identifier")

    if not db_master_prompt_instructions or not db_master_prompt_instructions.strip():
        log(f"AI_PROMPT_V3_FLOW: Default CRM AI System Prompt '{db_prompt_name}' has empty content.", "error")
        frappe.throw(_("Default AI System Prompt ('{0}') content is empty.").format(db_prompt_name), title="Configuration Error")
        return None, None # Defensive return after throw

    log(f"AI_PROMPT_V3_FLOW: Fetched default AI System Prompt: '{db_prompt_name}'. Model: '{db_model_identifier}'. DB Instructions (len {len(db_master_prompt_instructions)}): {db_master_prompt_instructions[:100]}...", "debug")

    # 2. Prepare ONLY Lead-Specific Data Block & other context for Jinja
    log("AI_PROMPT_V3_FLOW: Preparing lead details and Jinja context...", "debug")
    
    lead_display_name_str = f"{lead_fields_dict.get('first_name', '')} {lead_fields_dict.get('last_name', '')}".strip() or lead_fields_dict.get('name', 'Valued Contact')
    
    json_relevant_lead_fields = {}
    for k, v in lead_fields_dict.items():
        if not k.startswith(("_", "idx", "naming_series", "image", "timeline_hash")) and k not in [
            "amended_from", "docstatus", "doctype", "modified_by", "owner", "parent", 
            "parentfield", "parenttype", "creation", "modified"
        ] and v is not None:
            json_relevant_lead_fields[k] = v
    lead_all_fields_json_str = json.dumps(json_relevant_lead_fields, indent=2, cls=CustomJSONEncoder, ensure_ascii=False)
    log(f"AI_PROMPT_V3_FLOW: Lead JSON data prepared (length: {len(lead_all_fields_json_str)}).", "debug")

    # Explicitly build the standalone block string by string to avoid complex f-string issues.
    lead_details_standalone_block_parts = []
    lead_details_standalone_block_parts.append("--- Lead Information ---")
    lead_details_standalone_block_parts.append(f"Name: {lead_display_name_str}")
    lead_details_standalone_block_parts.append(f"Email: {lead_fields_dict.get('email_id') or lead_fields_dict.get('email', 'N/A')}")
    lead_details_standalone_block_parts.append(f"Organization: {lead_fields_dict.get('organization', 'N/A')}")
    lead_details_standalone_block_parts.append(f"Job Title: {lead_fields_dict.get('job_title', 'N/A')}")
    lead_details_standalone_block_parts.append(f"Industry: {lead_fields_dict.get('industry', 'N/A')}")
    lead_details_standalone_block_parts.append("\nFull Lead Data (JSON format for AI reference if needed):")
    lead_details_standalone_block_parts.append(lead_all_fields_json_str)
    lead_details_standalone_block = "\n".join(lead_details_standalone_block_parts)

    # 3. Render the Database Prompt (allowing it to use Jinja to embed lead data and UI inputs)
    # Simplified lead_summary_text construction
    _lead_org = lead_fields_dict.get('organization', 'N/A')
    _lead_title = lead_fields_dict.get('job_title', 'N/A')
    lead_summary_text_val = f"Lead: {lead_display_name_str}, Org: {_lead_org}, Title: {_lead_title}"

    jinja_context_for_db_prompt = {
        'lead_summary_text': lead_summary_text_val,
        'lead_data_json': lead_all_fields_json_str,
        'lead_raw_dict': lead_fields_dict,
        'user_requested_tone': ui_tone_preference,
        'user_additional_instructions': ui_additional_context,
        'current_frappe_user': frappe.session.user
    }
    # Using the simplified logging that was confirmed to be okay before.
    log(f"AI_PROMPT_V3_FLOW: Jinja context for DB prompt prepared. Keys: {list(jinja_context_for_db_prompt.keys())}", "debug")

    try:
        rendered_db_instructions = frappe.render_template(db_master_prompt_instructions, jinja_context_for_db_prompt)
        log(f"AI_PROMPT_V3_FLOW: Rendered DB master instructions using Jinja. Length: {len(rendered_db_instructions)}", "debug")
    except Exception as render_err:
        log(f"AI_PROMPT_V3_FLOW: Error rendering DB master instructions as Jinja template: {str(render_err)}. Using raw DB instructions.", "warning")
        rendered_db_instructions = db_master_prompt_instructions

    main_prompt_body = rendered_db_instructions

    # 4. Append lead_details_standalone_block IF it wasn't already incorporated by Jinja rendering
    if lead_all_fields_json_str not in main_prompt_body:
        main_prompt_body += "\n\n" + lead_details_standalone_block
        log(f"AI_PROMPT_V3_FLOW: Appended lead_details_standalone_block as JSON segment not found in rendered DB prompt.", "debug")
    else:
        log(f"AI_PROMPT_V3_FLOW: Lead details (JSON segment) seem to be included via Jinja in DB prompt. Standalone block not appended.", "debug")

    # 5. Append JSON Output Instruction (always, this is not optional)
    json_output_directive = (
        "\n\n--- MANDATORY OUTPUT FORMAT ---"
        "\nYour entire response MUST be a single, valid JSON object."
        "\nThis JSON object MUST contain exactly two fields:"
        "\n1. \"subject\": A string for the email subject."
        "\n2. \"content\": A string containing the complete email body, formatted as HTML (e.g., using <p>, <ul>, <li>, <strong> tags, etc.)."
        "\nExample of valid JSON output:"
        "\n{\n  \"subject\": \"Regarding Your Recent Inquiry About Product X\","
        "\n  \"content\": \"<p>Dear User,</p><p>Thank you for your interest...</p>\""
        "\n}"
        "\nDo NOT include any text or explanations outside of this JSON object."
    )
    
    final_prompt_to_ai = main_prompt_body + json_output_directive

    log(f"AI_PROMPT_V3_FLOW: Final prompt assembled. Total length: {len(final_prompt_to_ai)}", "info")
    log(f"AI_PROMPT_V3_FLOW: Final prompt (first 300 chars): {final_prompt_to_ai[:300]}...", "debug")
    
    return final_prompt_to_ai, db_model_identifier

def call_openrouter_api(prompt, api_key, model_identifier=None):
    """ (V3 Logic) Generate content using OpenRouter AI with specified model."""
    
    final_model_to_use = model_identifier if model_identifier and model_identifier.strip() else "openai/gpt-4o"
    log(f"AI_PROMPT_V3_FLOW: call_openrouter_api - START. Model: '{final_model_to_use}'. Prompt (first 50 chars): {prompt[:50]}...", "info")
    
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        headers = {
            "HTTP-Referer": frappe.utils.get_url(), # Use actual site URL
            "X-Title": "Sinx CRM AI Email" 
        }
        
        log(f"AI_PROMPT_V3_FLOW: Sending request to OpenRouter. Model: {final_model_to_use}", "debug")
        completion = client.chat.completions.create(
            extra_headers=headers,
            model=final_model_to_use, 
            messages=[
                {"role": "system", "content": "You are an AI assistant. Follow the user's instructions carefully and precisely, especially regarding output format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7, 
            max_tokens=2048, # Increased for potentially complex HTML + subject
            response_format={"type": "json_object"} 
        )
        
        response_content_str = completion.choices[0].message.content
        log(f"AI_PROMPT_V3_FLOW: Raw response from OpenRouter (model {final_model_to_use}). Length: {len(response_content_str)}", "debug")
        log(f"AI_PROMPT_V3_FLOW: Raw response content (first 100 chars): {response_content_str[:100]}...", "debug")
        
        try:
            content_json = json.loads(response_content_str)
            log(f"AI_PROMPT_V3_FLOW: Successfully parsed JSON response from AI. Keys: {', '.join(content_json.keys())}", "debug")
        except json.JSONDecodeError as e_json:
            log(f"AI_PROMPT_V3_FLOW: JSONDecodeError from OpenRouter (model {final_model_to_use}): {str(e_json)}", "error")
            log(f"AI_PROMPT_V3_FLOW: Faulty JSON string from AI (first 500 chars): {response_content_str[:500]}", "error")
            return {
                "success": False,
                "message": f"AI returned malformed JSON. Response from AI was: '{response_content_str[:200]}...'. Error: {str(e_json)}"
            }

        subject = content_json.get("subject")
        email_body_html = content_json.get("content")

        if subject is None or email_body_html is None:
            missing_fields_str = ", ".join(f for f in ["subject", "content"] if content_json.get(f) is None)
            log(f"AI_PROMPT_V3_FLOW: AI JSON response missing required field(s): '{missing_fields_str}'. Keys found: {', '.join(content_json.keys())}", "error")
            return {
                "success": False,
                "message": f"AI response was valid JSON but missing required fields: {missing_fields_str}. Check AI's adherence to output format instructions."
            }
        
        log(f"AI_PROMPT_V3_FLOW: call_openrouter_api - SUCCESS. Subject: '{subject[:50]}...'", "info")
        return {
            "success": True,
            "subject": subject,
            "content": email_body_html
        }
        
    except Exception as e_api:
        log(f"AI_PROMPT_V3_FLOW: Error during OpenRouter API call (model {final_model_to_use}): {str(e_api)}", "error")
        log(f"AI_PROMPT_V3_FLOW: Traceback: {frappe.get_traceback()}", "error")
        return {
            "success": False,
            "message": f"Error during OpenRouter API call ({final_model_to_use}): {str(e_api)}"
        }

@frappe.whitelist()
def send_test_email(lead_name, email_content, subject, recipient_email="sanchayt@sinxsolutions.ai"):
    """Send a test email with the generated content using Resend API"""
    log(f"Sending test email for lead {lead_name} to {recipient_email}", "info")
    
    try:
        lead = frappe.get_doc("CRM Lead", lead_name)
        
        # Get Resend API key from environment
        api_key = os.getenv("RESEND_API_KEY")
        default_from = os.getenv("RESEND_DEFAULT_FROM")
        
        # Get current user information
        try:
            user = frappe.get_doc("User", frappe.session.user)
            sender_name = user.full_name or os.getenv("SENDER_NAME") or "Sinx Solutions"
        except Exception:
            sender_name = os.getenv("SENDER_NAME") or "Sinx Solutions"
        
        # Log loaded variables (mask key partially)
        masked_key = f"{api_key[:5]}...{api_key[-4:]}" if api_key and len(api_key) > 9 else "Not found or too short"
        log(f"Loaded RESEND_API_KEY: {masked_key}", "debug")
        log(f"Loaded RESEND_DEFAULT_FROM: {default_from}", "debug")
        log(f"Using sender name: {sender_name}", "debug")
        
        if not api_key:
            log("Resend API Key not found in environment variables (.env file).", "error")
            return {
                "success": False,
                "message": "Resend API Key missing"
            }
        
        resend.api_key = api_key
        
        final_from = default_from or "info@sinxsolutions.ai"
        log(f"Using 'From' address: {final_from}", "debug")
        
        # Create email template and wrap AI content in it
        lead_first_name = lead.first_name or "there"
        html_template = get_email_template(subject)
        rendered_html = html_template.replace("{ name }", lead_first_name)
        rendered_html = rendered_html.replace("{ sender_name }", sender_name)
        rendered_html = rendered_html.replace("{ email_body_content }", email_content)
        
        log("Email template applied to AI content", "debug")
                
        # Resend email params
        params = {
            "from": final_from,
            "to": [recipient_email],
            "subject": subject,
            "html": rendered_html,  # Use the rendered HTML with the template
        }
        
        log(f"Prepared Resend params for sending", "debug")
        
        # Send the email
        log("Sending email via Resend API...", "debug")
        email_response = resend.Emails.send(params)
        log(f"Resend API raw response: {json.dumps(email_response, default=str)}", "debug")
        
        if email_response.get('id'):
            log(f"Email sent successfully via Resend (ID: {email_response.get('id')})", "info")
            return {
                "success": True,
                "message": f"Test email sent to {recipient_email}"
            }
        else:
            error_message = f"Resend failed: {email_response.get('message', 'Unknown error')}"
            log(error_message, "error")
            return {
                "success": False,
                "message": error_message
            }
        
    except Exception as e:
        log(f"Error sending test email: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error sending test email: {str(e)}"
        }

def get_email_template(subject="Introduction from Sinx Solutions"):
    """Get HTML email template with styling using unique placeholders."""
    primary_blue = "#005ea6" 
    secondary_blue = "#007bff" 
    light_blue_bg = "#f0f7ff" 
    container_bg = "#ffffff" 
    dark_text = "#333333"
    light_text = "#ffffff"
    footer_text = "#777777"
    border_color = "#dee2e6"

    # Use unique placeholders unlikely to clash with HTML/CSS/JS
    placeholder_body = "__AI_EMAIL_BODY_CONTENT__"
    placeholder_sender = "__SENDER_FULL_NAME__"

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="X-UA-Compatible" content="ie=edge">
        <title>{subject}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body {{ margin: 0; padding: 0; width: 100% !important; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; background-color: {light_blue_bg}; font-family: 'Inter', sans-serif; }}
            .email-container {{ width: 100%; max-width: 640px; margin: 40px auto; background-color: {container_bg}; border-radius: 12px; overflow: hidden; border: 1px solid {border_color}; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            .header {{ background-color: {primary_blue}; padding: 25px 30px; text-align: center; }}
            .header h1 {{ margin: 10px 0 0 0; font-size: 26px; font-weight: 700; color: {light_text}; }}
            .content {{ padding: 35px 40px; color: {dark_text}; font-size: 16px; line-height: 1.7; }}
            .content p {{ margin: 0 0 18px 0; }}
            .content .salutation {{ font-weight: 600; margin-bottom: 20px; }}
            .content .closing {{ margin-top: 25px; }}
            .content strong {{ font-weight: 600; color: {dark_text}; }}
            .content a {{ color: {secondary_blue}; text-decoration: underline; font-weight: 600; }}
            .signature {{ margin-top: 25px; padding-top: 15px; border-top: 1px solid {border_color}; }}
            .signature p {{ margin: 0 0 5px 0; font-size: 15px; line-height: 1.5; font-weight: 600; color: {primary_blue}; }}
            .signature .sender-title {{ font-size: 14px; color: {dark_text}; font-weight: 400; }}
            .footer {{ background-color: {light_blue_bg}; padding: 20px 30px; text-align: center; font-size: 13px; color: {footer_text}; border-top: 1px solid {border_color}; }}
            .footer a {{ color: {secondary_blue}; text-decoration: none; }}
            @media only screen and (max-width: 640px) {{
                .email-container {{ width: 95% !important; margin: 20px auto !important; border-radius: 8px; }}
                .content {{ padding: 25px 20px; font-size: 15px; }}
                .header {{ padding: 20px; }}
                .header h1 {{ font-size: 22px; }}
                .footer {{ padding: 15px 20px; font-size: 12px; }}
            }}
        </style>
    </head>
    <body style="background-color: {light_blue_bg};">
        <div class="email-container">
            <div class="header">
                 <h1 style="color: {light_text};">Sinx Solutions</h1> 
            </div>
            <div class="content">
                
                <!-- AI Generated Content Placeholder -->
                {placeholder_body}
                
                <div class="signature">
                    <p style="color: {primary_blue};"><strong style="color: {primary_blue};">{placeholder_sender}</strong></p>
                    <p class="sender-title" style="color: {dark_text};">Sinx Solutions</p> 
                </div>
            </div>
            <div class="footer">
                <p style="margin-bottom: 5px;">Sinx Solutions | <a href="https://sinxsolutions.ai">sinxsolutions.ai</a></p>
                <p style="margin:0;"><small>© 2025 Sinx Solutions</small></p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_template

def render_full_email(ai_generated_body: str, lead_data: dict, sender_name: str, subject: str) -> str:
    """Renders the full email HTML by injecting AI content into the base template using unique placeholders."""
    base_template = get_email_template(subject=subject)
    
    # Use unique placeholders defined in get_email_template
    placeholder_body = "__AI_EMAIL_BODY_CONTENT__"
    placeholder_sender = "__SENDER_FULL_NAME__"
    
    # Ensure sender_name is a string
    real_sender_name = str(sender_name or "Sinx Solutions")
    
    # Debug the replacement values
    log(f"Email template values - sender_name: '{real_sender_name}'", "debug")
    log(f"AI content length for replacement: {len(ai_generated_body)}", "debug")
    
    # Replace unique placeholders in base template
    rendered_html = base_template
    rendered_html = rendered_html.replace(placeholder_body, ai_generated_body)
    rendered_html = rendered_html.replace(placeholder_sender, real_sender_name)
    
    log("Email template rendering completed with unique placeholders", "debug")
    
    return rendered_html

@frappe.whitelist()
def generate_bulk_emails(filter_json=None, selected_leads=None, selected_template_name=None, test_mode=1):
    """Initiates a bulk email job using a selected Frappe Email Template.
    
    Args:
        filter_json (str, optional): JSON string of list view filters if selected_leads is not provided.
        selected_leads (str, optional): JSON string array of specific lead names to process.
        selected_template_name (str, optional): The name of the Frappe Email Template to use.
        test_mode (int, optional): 1 for test mode (sends to user), 0 for live. Defaults to 1.
    
    Returns:
        dict: Response with job ID or error message.
    """
    init_environment()
    log(f"==== BULK EMAIL (TEMPLATE BASED) START ====", "info")
    log(f"PARAMS: filter_json='{filter_json}', selected_leads='{selected_leads}', template='{selected_template_name}', test_mode={test_mode}", "info")

    if not selected_template_name:
        log("ERROR: No email template selected for bulk send.", "error")
        return {"success": False, "message": _("Please select an email template.")}

    # Convert test_mode to boolean more robustly
    is_test_mode = True
    if isinstance(test_mode, str):
        is_test_mode = test_mode.lower() == 'true' or test_mode == '1'
    elif isinstance(test_mode, (int, float)):
        is_test_mode = bool(test_mode)
    log(f"Processed test_mode: {is_test_mode} (original: {test_mode})", "debug")

    try:
        leads_to_process = []
        if selected_leads:
            try:
                lead_names = json.loads(selected_leads)
                if not isinstance(lead_names, list):
                    raise ValueError("selected_leads should be a JSON array of names.")
                # Fetch minimal lead data for these names
                leads_to_process = frappe.get_list("CRM Lead", 
                                                filters={"name": ("in", lead_names)},
                                                fields=["name", "email"], # Only need name and email for the job
                                                limit_page_length=len(lead_names) + 10) # Fetch all selected
                log(f"Fetched {len(leads_to_process)} leads based on selected_leads array.", "info")
            except Exception as e:
                log(f"Error processing selected_leads JSON: {str(e)}", "error")
                return {"success": False, "message": f"Invalid selected_leads format: {str(e)}"}
        elif filter_json:
            try:
                filters = json.loads(filter_json)
                leads_to_process = frappe.get_list("CRM Lead", 
                                                filters=filters,
                                                fields=["name", "email"],
                                                limit_page_length=1000) # Safety limit for filter-based
                log(f"Fetched {len(leads_to_process)} leads based on filter_json.", "info")
            except json.JSONDecodeError as e:
                log(f"Error parsing filter_json: {str(e)}", "error")
                return {"success": False, "message": f"Invalid filter_json format: {str(e)}"}
        else:
            log("ERROR: Neither selected_leads nor filter_json provided for bulk email.", "error")
            return {"success": False, "message": _("No leads specified for bulk email.")}

        lead_count = len(leads_to_process)
        if lead_count == 0:
            log("No leads found matching criteria for bulk email.", "warning")
            return {"success": False, "message": _("No leads found to send emails to.")}

        log(f"Enqueueing bulk email job for {lead_count} leads using template '{selected_template_name}'. TestMode: {is_test_mode}", "info")
        job = enqueue(
            process_bulk_emails, # This function will now primarily use the template
            queue="long",
            timeout=3600, 
            leads_data=leads_to_process, # Pass the list of lead dicts {name, email}
            selected_template_name=selected_template_name,
            test_mode=is_test_mode,
            # Remove deprecated/unused: tone, additional_context
        )
        
        job_id = job.id
        log(f"Bulk email job enqueued. ID: {job_id}", "info")

        # Job tracking (simplified, focusing on RQ job ID)
        job_meta_data = {
            "job_id": job_id,
            "status": "queued",
            "leads_count": lead_count,
            "template_name": selected_template_name,
            "test_mode": is_test_mode,
            "user": frappe.session.user,
            "timestamp": now_datetime(),
            "progress": 0,
            "successful_leads_details": [],
            "failed_leads_details": []
        }
        job_meta_key = f"crm:bulk_email:job:{job_id}"
        frappe.cache().set_value(job_meta_key, job_meta_data, expires_in_sec=86400) # 24 hours TTL
        log(f"Job metadata stored in Redis: {job_meta_key}", "debug")

        return {
            "success": True,
            "message": _("Bulk email job for {0} leads using template '{1}' has been started.").format(lead_count, selected_template_name),
            "job_id": job_id
        }

    except Exception as e:
        log(f"Error in generate_bulk_emails: {str(e)}", "error")
        log(f"Traceback: {frappe.get_traceback()}", "error")
        return {"success": False, "message": f"Error initiating bulk email job: {str(e)}"}


def process_bulk_emails(leads_data, selected_template_name, test_mode=True, **kwargs):
    """Processes bulk emails using a selected Frappe Email Template.
    This function is executed by an RQ worker.
    Args:
        leads_data (list): List of dicts, each containing lead 'name' and 'email'.
        selected_template_name (str): The name of the Frappe Email Template to use.
        test_mode (bool): If True, emails are sent to the default outgoing email address.
    """
    init_environment()
    from rq import get_current_job
    current_job = get_current_job()
    job_id = current_job.id if current_job else frappe.generate_hash(length=10)
    job_log = lambda msg, level="info": log(f"[Job {job_id}] {msg}", level)

    job_log(f"Starting bulk processing for {len(leads_data)} leads using template '{selected_template_name}'. TestMode: {test_mode}", "info")
    
    job_meta_key = f"crm:bulk_email:job:{job_id}"
    job_data = frappe.cache().get_value(job_meta_key) or {}
    job_data.update({
        "job_id": job_id, "status": "running",
        "leads_count": len(leads_data),
        "template_name": selected_template_name,
        "test_mode": test_mode,
        "timestamp": job_data.get("timestamp", now_datetime()),
        "successful_leads_details": job_data.get("successful_leads_details", []),
        "failed_leads_details": job_data.get("failed_leads_details", [])
    })
    frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)

    total_leads = len(leads_data)
    for i, lead_info in enumerate(leads_data):
        lead_name = lead_info.get("name")
        progress = int(((i + 1) / total_leads) * 100)
        job_data["progress"] = progress
        # frappe.publish_realtime(...) for progress can be added here if needed

        if not lead_name:
            job_log(f"Skipping lead at index {i} due to missing name.", "warning")
            job_data["failed_leads_details"].append({"name": "Unknown", "error": "Missing lead name in data"})
            continue
        
        try:
            job_log(f"Processing lead {i+1}/{total_leads}: {lead_name}", "info")
            # Call generate_email_for_lead, now it needs to handle template name
            result = generate_email_for_lead(
                lead_name=lead_name, 
                selected_template_name=selected_template_name, 
                test_mode=test_mode,
                # ai_tone and ai_additional_context are not passed, so AI path won't be taken
            )

            if result.get("success"): # generate_email_for_lead now returns overall success
                job_log(f"Successfully processed and sent email for lead {lead_name}", "info")
                job_data["successful_leads_details"].append({"name": lead_name, "communication_id": result.get("communication_id")})
            else:
                error_msg = result.get("message", "Unknown error during processing")
                job_log(f"Failed for lead {lead_name}: {error_msg}", "error")
                job_data["failed_leads_details"].append({"name": lead_name, "error": error_msg, "communication_id": result.get("communication_id")})
        
        except Exception as e:
            job_log(f"CRITICAL LOOP ERROR for lead {lead_name}: {str(e)}", "error")
            job_log(f"TRACEBACK: {frappe.get_traceback()}", "error")
            job_data["failed_leads_details"].append({"name": lead_name, "error": f"Loop error: {str(e)}"})
        
        finally:
            frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
            time.sleep(0.2) # Small delay between processing each lead

    job_data["status"] = "completed" if not job_data["failed_leads_details"] else "completed_with_errors"
    job_data["progress"] = 100
    job_data["completed_at"] = now_datetime()
    frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
    job_log(f"Bulk job finished. Success: {len(job_data['successful_leads_details'])}, Failed: {len(job_data['failed_leads_details'])}", "info")
    # frappe.publish_realtime(...) for completion can be added here

    return {
        "success": not job_data["failed_leads_details"],
        "message": f"Processed {total_leads} leads. Success: {len(job_data['successful_leads_details'])}, Failed: {len(job_data['failed_leads_details'])}",
        "details": {
            "successful": job_data['successful_leads_details'],
            "failed": job_data['failed_leads_details']
        }
    }


def generate_email_for_lead(lead_name, selected_template_name=None, test_mode=True, ai_tone=None, ai_additional_context=None):
    """ (V3 Logic) Generates and sends an email for a single lead.
    If selected_template_name (Frappe Email Template) is provided, it's used (Jinja).
    Else, if ai_tone is provided, AI is used based on default CRM AI System Prompt (V3 logic).
    """
    init_environment()
    log(f"AI_PROMPT_V3_FLOW: generate_email_for_lead (V3) - START. Lead: '{lead_name}', FrappeTemplate: '{selected_template_name}', AITone: '{ai_tone}', TestMode: {test_mode}", "info")

    communication_id = None
    final_subject = "Error: Email Subject Not Set" 
    final_html_for_sendmail = "<p>Error: Email content could not be generated.</p>"
    overall_success = False 
    is_content_ai_generated = False

    try:
        lead = frappe.get_doc("CRM Lead", lead_name)
        if not lead.email: 
            log(f"AI_PROMPT_V3_FLOW: Lead '{lead_name}' has no email address. Aborting.", "error")
            raise ValueError(f"Lead '{lead_name}' has no email address.")

        sender_user = frappe.session.user or "Administrator"
        sender_email_address = get_formatted_email(sender_user)
        sender_full_name_val = frappe.db.get_value("User", sender_user, "full_name") or "Sinx Solutions Team"
        default_email_account_name = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "name")
        
        log(f"AI_PROMPT_V3_FLOW: Sender: {sender_email_address} ({sender_full_name_val}), Default Outgoing Account: {default_email_account_name}", "debug")
        if not default_email_account_name:
            log("AI_PROMPT_V3_FLOW: No default outgoing Frappe Email Account configured. Aborting.", "error")
            raise ValueError("No default outgoing Frappe Email Account configured.")

        recipient_email_actual = lead.email
        recipient_for_sendmail = recipient_email_actual
        if test_mode:
            test_recipient_email = frappe.db.get_value("User", sender_user, "email")
            if not test_recipient_email: test_recipient_email = frappe.conf.get("test_email_recipient")
            if not test_recipient_email:
                log("AI_PROMPT_V3_FLOW: Test mode error: No test recipient email found (User or site_config.json:test_email_recipient).", "error")
                raise ValueError("Test mode active, but no test recipient email found.")
            recipient_for_sendmail = test_recipient_email
            log(f"AI_PROMPT_V3_FLOW: TEST MODE. Email for Lead '{lead_name}' (Actual: {recipient_email_actual}) will be sent to '{recipient_for_sendmail}'", "info")

        if selected_template_name: 
            log(f"AI_PROMPT_V3_FLOW: Using Frappe Email Template (Jinja): '{selected_template_name}' for lead '{lead_name}'", "info")
            is_content_ai_generated = False
            template_doc = frappe.get_doc("Email Template", selected_template_name)
            jinja_context = {"doc": lead.as_dict()} 
            final_subject = frappe.render_template(template_doc.subject, jinja_context)
            # Standard Frappe templates usually produce full HTML, so no render_full_email needed here.
            final_html_for_sendmail = frappe.render_template(template_doc.response_, jinja_context)
            log(f"AI_PROMPT_V3_FLOW: Rendered Frappe Email Template '{selected_template_name}'. Subject: '{final_subject}'", "debug")
        
        elif ai_tone: 
            log(f"AI_PROMPT_V3_FLOW: Using AI (V3 logic) for '{lead_name}'. UI Tone: '{ai_tone}'", "info")
            is_content_ai_generated = True
            
            openrouter_api_key = os.getenv("OPENROUTER_KEY")
            if not openrouter_api_key: # Should be caught by generate_email_content, but defensive check.
                log("AI_PROMPT_V3_FLOW: OpenRouter API key not configured. Aborting.", "error")
                raise ValueError("OpenRouter API key not configured.")
            
            log(f"AI_PROMPT_V3_FLOW: Calling construct_prompt (V3) for AI generation for lead '{lead.name}'", "debug")
            prompt_to_send_ai, model_id_for_ai = construct_prompt(lead.as_dict(), ai_tone, ai_additional_context)
            
            log(f"AI_PROMPT_V3_FLOW: Calling call_openrouter_api with model '{model_id_for_ai}' for lead '{lead.name}'", "debug")
            ai_api_response = call_openrouter_api(prompt_to_send_ai, openrouter_api_key, model_id_for_ai)

            if not ai_api_response.get("success"):
                error_msg = ai_api_response.get('message', "Unknown AI API error during content generation.")
                log(f"AI_PROMPT_V3_FLOW: AI API call failed for lead '{lead.name}': {error_msg}", "error")
                raise ValueError(f"AI API call failed: {error_msg}")
            
            final_subject = ai_api_response.get("subject")
            ai_generated_body_html = ai_api_response.get("content")

            if final_subject is None or ai_generated_body_html is None:
                log(f"AI_PROMPT_V3_FLOW: AI response missing 'subject' or 'content' for lead '{lead.name}'. Response: {ai_api_response}", "error")
                raise ValueError("AI response from call_openrouter_api was successful but missing 'subject' or 'content' fields.")
            
            log(f"AI_PROMPT_V3_FLOW: AI content generated. Subject: '{final_subject}'. Body HTML length: {len(ai_generated_body_html)}", "debug")
            
            # Wrap the AI-generated body HTML with the standard email template/shell
            log(f"AI_PROMPT_V3_FLOW: Wrapping AI-generated body HTML with render_full_email for lead '{lead.name}'", "debug")
            final_html_for_sendmail = render_full_email(
                ai_generated_body=ai_generated_body_html, 
                lead_data=lead.as_dict(), 
                sender_name=sender_full_name_val, # Use the acting Frappe user's name for the template wrapper
                subject=final_subject
            )
            log(f"AI_PROMPT_V3_FLOW: AI content wrapped in full HTML email structure. Total length: {len(final_html_for_sendmail)}", "debug")
        else:
            log(f"AI_PROMPT_V3_FLOW: Error for lead '{lead.name}' - Method unclear: No Frappe Template and no AI Tone.", "error")
            raise ValueError("Email generation method unclear: No Frappe template selected and AI tone not specified.")

        log(f"AI_PROMPT_V3_FLOW: Creating Communication record for lead '{lead.name}'. Recipient: '{recipient_for_sendmail}'", "info")
        comm_doc = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "subject": final_subject,
            "content": final_html_for_sendmail, # This is the full HTML (possibly wrapped)
            "text_content": html2text(final_html_for_sendmail), 
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": sender_email_address,
            "sender_full_name": sender_full_name_val,
            "recipients": recipient_for_sendmail, 
            "actual_recipient": recipient_email_actual if test_mode and recipient_for_sendmail != recipient_email_actual else None,
            "email_status": "Open", 
            "sent_or_received": "Sent",
            "email_account": default_email_account_name,
            "is_ai_generated": 1 if is_content_ai_generated else 0
        })
        comm_doc.insert(ignore_permissions=True) 
        communication_id = comm_doc.name
        log(f"AI_PROMPT_V3_FLOW: Communication record {communication_id} created. Is AI: {is_content_ai_generated}", "info")

        email_send_args = {
            "recipients": recipient_for_sendmail,
            "sender": sender_email_address,
            "subject": final_subject,
            "message": final_html_for_sendmail, # Send the final, possibly wrapped, HTML
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "communication": communication_id,
            "now": True 
        }
        log(f"AI_PROMPT_V3_FLOW: Queuing email (Comm ID {communication_id}) via frappe.sendmail. Args: {json.dumps(email_send_args, default=str)}", "debug")
        frappe.sendmail(**email_send_args)
        frappe.db.commit() 
        log(f"AI_PROMPT_V3_FLOW: frappe.sendmail called and db.commit() for Comm ID {communication_id}.", "info")
        
        frappe.db.set_value("Communication", communication_id, "email_status", "Sent")
        frappe.db.commit() 
        log(f"AI_PROMPT_V3_FLOW: Communication {communication_id} status updated to 'Sent'.", "info")
        overall_success = True

    except frappe.DoesNotExistError as e_dnf:
        error_msg = f"Lead '{lead_name}' not found in generate_email_for_lead: {str(e_dnf)}"
        log(f"AI_PROMPT_V3_FLOW: {error_msg}", "error")
        return {"success": False, "message": error_msg, "communication_id": None}
    except Exception as e_general:
        error_msg = f"Error in generate_email_for_lead for '{lead_name}': {str(e_general)}"
        log(f"AI_PROMPT_V3_FLOW: {error_msg}", "error")
        log(f"AI_PROMPT_V3_FLOW: TRACEBACK: {frappe.get_traceback()}", "error")
        if communication_id:
            try:
                frappe.db.set_value("Communication", communication_id, "email_status", "Error")
                frappe.db.set_value("Communication", communication_id, "error_details", error_msg) 
                frappe.db.commit()
                log(f"AI_PROMPT_V3_FLOW: Comm {communication_id} status set to 'Error'.", "warning")
            except Exception as db_update_err:
                log(f"AI_PROMPT_V3_FLOW: Failed to update comm {communication_id} to Error: {str(db_update_err)}", "error")
        
        if not frappe.exc_already_raised:
             pass 
        return {"success": False, "message": error_msg, "communication_id": communication_id}
    
    log(f"AI_PROMPT_V3_FLOW: generate_email_for_lead (V3) - FINISHED for '{lead_name}'. Success: {overall_success}", "info")
    return {"success": overall_success, 
            "message": "Email processed successfully" if overall_success else f"Email processing failed for {lead_name}", 
            "communication_id": communication_id}

@frappe.whitelist()
def get_bulk_email_job_status(job_id=None):
    """Get the status of a bulk email job
    
    Args:
        job_id (str, optional): Job ID to check. Defaults to None.
    
    Returns:
        dict: Job status information
    """
    if not job_id:
        frappe.throw(_("Job ID is required"))
    
    job_data = {"job_id": job_id, "status": "unknown"} # Default in case of error
    try:
        # Import Redis Queue
        import redis
        from rq import Queue
        from frappe.utils.background_jobs import get_redis_conn
        from rq.job import Job
        
        # Debug logging for troubleshooting
        log(f"Checking job status for ID: {job_id}", "debug")
        
        # Get Redis connection
        conn = get_redis_conn()
        
        # Try to fetch the job directly by ID
        job = None
        try:
            job = Job.fetch(job_id, connection=conn)
            log(f"Job fetched directly by ID: {job_id}", "debug")
        except Exception as e:
            log(f"Error fetching job directly: {str(e)}", "debug")
            
            # If that fails, check if we need to strip/add site prefix
            if "||" in job_id:
                # Try without site prefix
                simple_id = job_id.split("||")[1]
                try:
                    job = Job.fetch(simple_id, connection=conn)
                    log(f"Job fetched with simple ID: {simple_id}", "debug")
                except Exception as e2:
                    log(f"Error fetching with simple ID: {str(e2)}", "debug")
            else:
                # Try with site prefix
                site_name = frappe.local.site
                full_id = f"{site_name}||{job_id}"
                try:
                    job = Job.fetch(full_id, connection=conn)
                    log(f"Job fetched with full ID: {full_id}", "debug")
                except Exception as e2:
                    log(f"Error fetching with full ID: {str(e2)}", "debug")
        
        # If still no job, try to find in other queues
        if not job:
            # Check in standard queues
            for queue_name in ['default', 'long', 'short', 'failed', 'finished']:
                try:
                    q = Queue(queue_name, connection=conn)
                    job = q.fetch_job(job_id)
                    if job:
                        log(f"Job found in '{queue_name}' queue", "debug")
                        break
                except Exception as e:
                    log(f"Error checking '{queue_name}' queue: {str(e)}", "debug")
                    continue
        
        # Get job metadata from Redis using both possible key formats
        job_meta = None
        site_name = frappe.local.site
        
        # Try all possible keys
        possible_keys = [
            f"crm:bulk_email:job:{job_id}",
            f"crm:bulk_email:job:{job_id.split('||')[1]}" if "||" in job_id else None,
            f"crm:bulk_email:job:{site_name}||{job_id}" if "||" not in job_id else None,
            f"bulk_email_job_{job_id}",
            f"bulk_email_job_{job_id.split('||')[1]}" if "||" in job_id else None
        ]
        
        for key in possible_keys:
            if not key:
                continue
                    
            try:
                log(f"Trying to get job meta with key: {key}", "debug")
                job_meta_raw = frappe.cache().get_value(key)
                if job_meta_raw:
                    log(f"Found job metadata with key: {key}", "debug")
                    if isinstance(job_meta_raw, dict):
                        job_meta = job_meta_raw
                    else:
                        try: 
                            job_meta = json.loads(job_meta_raw)
                        except (json.JSONDecodeError, TypeError):
                            log(f"Could not parse job meta from key {key}", "warning")
                    break
                    
                # Try direct Redis get if cache fails
                meta_str = conn.get(key)
                if meta_str:
                    try:
                        job_meta = json.loads(meta_str.decode('utf-8'))
                        log(f"Found job metadata directly in Redis with key: {key}", "debug")
                        break
                    except (json.JSONDecodeError, TypeError):
                         log(f"Could not parse job meta from redis key {key}", "warning")       
            except Exception as e:
                log(f"Error checking key {key}: {str(e)}", "debug")
        
        # Get job status
        job_status = "not_found"
        if job:
            try:
                job_status = job.get_status()
                log(f"Job status from RQ: {job_status}", "debug")
            except Exception as e:
                log(f"Error getting job status: {str(e)}", "debug")
                job_status = "error"
        
        # Prepare response
        job_data = {
            "job_id": job_id,
            "leads_count": job_meta.get("leads_count", 0) if job_meta else 0,
            "status": job_status,
            "progress": job_meta.get("progress", 0) if job_meta else 0,
            "timestamp": now_datetime(), # Use current time for status check time
            "successful_leads": job_meta.get("successful_leads_details", []) if job_meta else [], # Use detailed list
            "failed_leads": job_meta.get("failed_leads_details", []) if job_meta else [], # Use detailed list
            "error": job.exc_info if (job and hasattr(job, 'exc_info') and job.exc_info) else (job_meta.get("error") if job_meta else None)
        }
        
        return {
            "success": True,
            "job_data": job_data
        }
                
    except Exception as e:
        frappe.log_error(f"Error checking job status: {str(e)}")
        return {
            "success": False,
            "message": _("Error checking job status: {0}").format(str(e)),
            "job_data": job_data # Return default job data with status unknown/error
        }

@frappe.whitelist()
def list_bulk_email_jobs():
    """List all recent bulk email jobs"""
    try:
        # Get all keys matching the pattern
        all_keys = frappe.cache().get_keys("bulk_email_job_*")
        
        jobs = []
        for key in all_keys:
            # Extract job ID from key name
            job_id = key.replace("bulk_email_job_", "")
            
            # Get job data
            job_data_json = frappe.cache().get_value(key)
            if job_data_json:
                job_data = json.loads(job_data_json)
                
                # Add summary info
                summary = {
                    "job_id": job_id,
                    "status": job_data.get("status"),
                    "progress": job_data.get("progress"),
                    "timestamp": job_data.get("timestamp"),
                    "leads_count": job_data.get("leads_count"),
                    "success_count": len(job_data.get("successful_leads", [])),
                    "error_count": len(job_data.get("failed_leads", [])),
                    "user": job_data.get("user")
                }
                
                jobs.append(summary)
        
        # Sort by timestamp, newest first
        jobs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "success": True,
            "jobs": jobs
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error listing jobs: {str(e)}"
        }

@frappe.whitelist()
def get_last_bulk_email_leads():
    """Retrieve the last set of leads used for bulk email (for debugging purposes)"""
    leads_data = frappe.cache().get_value("last_bulk_email_leads")
    
    if not leads_data:
        return {
            "success": False,
            "message": "No cached leads data found. Please run bulk email generation first.",
            "leads": []
        }
    
    try:
        leads = json.loads(leads_data)
        return {
            "success": True,
            "count": len(leads),
            "leads": leads
        }
    except Exception as e:
        log(f"Error retrieving cached leads data: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error retrieving leads data: {str(e)}",
            "leads": []
        }

@frappe.whitelist()
def get_api_status():
    """Check if API keys are configured in .env file"""
    openrouter_key = os.getenv("OPENROUTER_KEY")
    resend_key = os.getenv("RESEND_API_KEY")
    test_email = os.getenv("RESEND_DEFAULT_FROM") or "sanchayt@sinxsolutions.ai"
    
    return {
        "success": True,
        "openai_configured": bool(openrouter_key),
        "resend_configured": bool(resend_key),
        "test_email": test_email
    }

@frappe.whitelist()
def send_ai_email(recipients, subject, content, doctype="CRM Lead", name=None, cc=None, bcc=None, force_resend=False, selected_template_name=None): # Added selected_template_name
    """Sends an email. 
    If selected_template_name is provided, it fetches that Frappe Email Template, 
    renders it using the lead data, and sends that. 
    Otherwise, it sends the raw content received from the frontend.
    """
    log(f"==== BACKEND: send_ai_email Sending START ====", "info")
    log(f"DETAILS: Recipients={recipients}, Subject={subject}, DocType={doctype}, Name={name}, Template='{selected_template_name}'", "info")
    log(f"BACKEND: Initial content received (first 200 chars): {content[:200]}...", "debug")
    
    final_subject = subject # Default subject from frontend
    final_message = content # Default message from frontend

    try:
        # --- Get Sender Info (Keep existing logic) --- 
        try:
            user = frappe.get_doc("User", frappe.session.user)
            sender_name = user.full_name or os.getenv("SENDER_NAME") or "Sinx Solutions"
            sender = frappe.session.user
            log(f"BACKEND: Using sender_name: {sender_name}, sender: {sender}", "info")
        except Exception as e:
            sender_name = os.getenv("SENDER_NAME") or "Sinx Solutions"
            sender = frappe.session.user
            log(f"BACKEND: Using fallback sender_name: {sender_name}, sender: {sender}", "info")
            log(f"BACKEND: Error getting user info: {str(e)}", "error")

        # --- Determine Final Subject and Message --- 
        if selected_template_name:
            log(f"BACKEND: Selected template specified: '{selected_template_name}'. Will use this template.", "info")
            try:
                # Fetch context document (e.g., Lead)
                doc_context = frappe.get_doc(doctype, name)
                doc_dict = doc_context.as_dict()
                
                # Fetch the specified Frappe Email Template
                template_doc = frappe.get_doc("Email Template", selected_template_name)
                log(f"BACKEND: Fetched Frappe Email Template: {template_doc.name}", "debug")

                # Prepare context for rendering template
                context = {"doc": doc_dict}
                log(f"BACKEND: Rendering context prepared. Keys: {list(context.keys())}", "debug")

                # Render template subject and body
                final_subject = frappe.render_template(template_doc.subject, context)
                final_message = frappe.render_template(template_doc.response_, context)
                log(f"BACKEND: Rendered template. Subject='{final_subject}', Message Length={len(final_message)}", "info")

            except Exception as template_error:
                log(f"BACKEND: ERROR rendering selected template '{selected_template_name}': {str(template_error)}", "error")
                log(f"BACKEND: Traceback: {frappe.get_traceback()}", "error")
                # Fallback: Send the raw content from editor with original subject in case of template error
                final_subject = subject
                final_message = content
                log(f"BACKEND: FALLBACK - Using raw content from editor due to template rendering error.", "warning")
                # Optional: Add error info to subject/message?
                # final_subject = f"[Template Error] {subject}"
                # final_message = f"<p><b>Error rendering template '{selected_template_name}': {str(template_error)}</b></p><hr/>{content}"
        else:
            log(f"BACKEND: No selected template. Using raw subject/content from editor.", "info")
            # final_subject and final_message are already set to frontend values

        # --- Format recipients (Keep existing logic) --- 
        recipient_list = recipients.split(',') if isinstance(recipients, str) else recipients
        recipient_list = [email.strip() for email in recipient_list]
        cc_list = []
        if cc:
            cc_list = cc.split(',') if isinstance(cc, str) else cc
            cc_list = [email.strip() for email in cc_list]
        bcc_list = []
        if bcc:
            bcc_list = bcc.split(',') if isinstance(bcc, str) else bcc
            bcc_list = [email.strip() for email in bcc_list]
        recipients_str = ", ".join(recipient_list) if isinstance(recipient_list, list) else recipient_list
        cc_str = ", ".join(cc_list) if isinstance(cc_list, list) and cc_list else ""
        bcc_str = ", ".join(bcc_list) if isinstance(bcc_list, list) and bcc_list else ""
        log(f"BACKEND: Formatted recipients='{recipients_str}', cc='{cc_str}', bcc='{bcc_str}'", "debug")
        
        # --- Convert final HTML to text (Keep existing logic) --- 
        text_content_for_communication = ""
        try:
            from frappe.utils.html_utils import html2text
            text_content_for_communication = html2text(final_message)
        except ImportError:
            try:
                from frappe.utils.html import html2text
                text_content_for_communication = html2text(final_message)
            except ImportError:
                import re
                def local_html2text(html_content_arg):
                    text = re.sub(r'<[^>]*>', ' ', html_content_arg)
                    return re.sub(r'\s+', ' ', text).strip()
                text_content_for_communication = local_html2text(final_message)

        # --- Create Communication (Use final_subject, final_message) --- 
        log("BACKEND: Creating communication record", "info")
        communication = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "sent_or_received": "Sent",
            "email_status": "Open",
            "subject": final_subject, # Use final determined subject
            "content": final_message, # Use final determined message
            "text_content": text_content_for_communication,
            "sender": sender,
            "sender_full_name": sender_name,
            "recipients": recipients_str,
            "cc": cc_str,
            "bcc": bcc_str,
            "reference_doctype": doctype,
            "reference_name": name,
            "seen": 1,
            "timeline_doctype": doctype,
            "timeline_name": name
        })
        communication.flags.ignore_permissions = True
        communication.flags.ignore_mandatory = True
        communication.insert()
        log(f"BACKEND: Communication created: {communication.name}", "info")
        
        # --- Create Communication Link (Keep existing logic) --- 
        log(f"BACKEND: Creating Communication Link for {doctype}/{name}", "info")
        comm_link = frappe.get_doc({
            "doctype": "Communication Link",
            "link_doctype": doctype,
            "link_name": name,
            "parent": communication.name,
            "parenttype": "Communication",
            "parentfield": "timeline_links"
        })
        comm_link.insert(ignore_permissions=True)
        log(f"BACKEND: Communication Link created successfully", "info")
            
        # --- Log final message before send (Keep existing logic) --- 
        log(f"BACKEND: Preparing to call frappe.sendmail", "debug")
        log(f"BACKEND: Recipients='{recipients_str}', Sender='{sender}', Subject='{final_subject}'", "debug")
        html_preview = final_message[:500] + ("..." if len(final_message) > 500 else "")
        log(f"BACKEND: Message HTML (first 500 chars + length: {len(final_message)}): {html_preview}", "debug")
        # log(f"BACKEND: FULL HTML MESSAGE TO SEND:\n{final_message}", "debug")
        
        # --- Send Email (Use final_subject, final_message) --- 
        log("BACKEND: Sending email via Frappe's sendmail", "info")
        frappe.sendmail(
            recipients=recipients_str,
            sender=sender,
            subject=final_subject, # Use final determined subject
            message=final_message, # Use final determined message
            communication=communication.name,
            reference_doctype=doctype,
            reference_name=name,
            cc=cc_str,
            bcc=bcc_str,
            now=True,
            expose_recipients="header"
        )
        
        frappe.db.commit()
        log(f"BACKEND: Email sent successfully and committed to database", "info")
        
        return {
            "success": True,
            "message": f"Email sent to {recipients}",
            "communication": communication.name
        }
        
    except Exception as e:
        log(f"==== BACKEND ERROR in send_ai_email: {str(e)} ====", "error")
        log(f"Error traceback: {frappe.get_traceback()}", "error")
        return {
            "success": False,
            "message": f"Error sending email: {str(e)}"
        }

@frappe.whitelist()
def get_email_preference():
    """Get the current email sending preference (Resend or Frappe)"""
    try:
        # Log to help with debugging
        frappe.log("Getting email preference...")
        
        # Check if a system setting exists for email preference
        email_preference = frappe.db.get_single_value(
            "System Settings", "crm_email_sending_service") or "resend"
        
        frappe.log(f"Retrieved email preference: {email_preference}")
        
        # Check if Frappe email is configured
        frappe_email_configured = False
        try:
            email_accounts = frappe.get_all("Email Account", 
                                           filters={"enabled": 1, "default_outgoing": 1},
                                           fields=["name", "email_id"])
            frappe_email_configured = len(email_accounts) > 0
            
            if frappe_email_configured:
                frappe.log(f"Found Frappe email account: {email_accounts[0].name}")
            else:
                frappe.log("No default outgoing Frappe email account found")
                
        except Exception as e:
            frappe.log(f"Error checking Frappe email: {str(e)}")
            frappe_email_configured = False
        
        # Check if Resend is configured
        resend_api_key = os.getenv("RESEND_API_KEY")
        resend_from = os.getenv("RESEND_DEFAULT_FROM")
        resend_configured = bool(resend_api_key) and bool(resend_from)
        
        if resend_configured:
            frappe.log(f"Resend is configured with from: {resend_from}")
        else:
            frappe.log("Resend API key or from email not configured")
        
        # If preference was not explicitly set but one system is configured, set it
        if not email_preference and (frappe_email_configured or resend_configured):
            if frappe_email_configured:
                email_preference = "frappe"
            else:
                email_preference = "resend"
                
            # Save the preference
            frappe.db.set_value("System Settings", "System Settings", 
                               "crm_email_sending_service", email_preference)
            frappe.db.commit()
            frappe.log(f"Auto-set email preference to: {email_preference}")
        
        return {
            "success": True,
            "email_preference": email_preference,
            "frappe_email_configured": frappe_email_configured,
            "resend_configured": resend_configured
        }
    except Exception as e:
        frappe.log(f"Error getting email preference: {str(e)}")
        return {
            "success": False,
            "email_preference": "resend",  # Default to Resend on error
            "frappe_email_configured": False,
            "resend_configured": bool(os.getenv("RESEND_API_KEY"))
        }

@frappe.whitelist()
def set_email_preference(preference):
    """Set the email sending preference (resend or frappe)"""
    if preference not in ["resend", "frappe"]:
        return {
            "success": False,
            "message": "Invalid preference. Use 'resend' or 'frappe'."
        }
    
    try:
        # Use Frappe's db_set method to save the setting
        frappe.db.set_value("System Settings", "System Settings", 
                           "crm_email_sending_service", preference)
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Email preference set to {preference}"
        }
    except Exception as e:
        log(f"Error setting email preference: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error setting preference: {str(e)}"
        }

@frappe.whitelist()
def get_ai_email_logs(limit=100):
    """Get the latest AI email logs for monitoring progress"""
    try:
        log_file_path = os.path.join(frappe.utils.get_bench_path(), "logs", "ai_email.log")
        
        if not os.path.exists(log_file_path):
            return {
                "success": False,
                "message": "AI email log file not found",
                "logs": []
            }
        
        # Read the log file from the end (latest logs first)
        logs = []
        with open(log_file_path, 'r') as file:
            all_lines = file.readlines()
            
            # Process all lines to identify complete log entries
            for line in all_lines[-limit*2:]:  # Read more lines to ensure we get enough actual entries
                if "AI Email:" in line:
                    # Parse log entry to extract timestamp and message
                    parts = line.strip().split("AI Email:", 1)
                    if len(parts) == 2:
                        timestamp = parts[0].strip()
                        message = parts[1].strip()
                        logs.append({
                            "timestamp": timestamp,
                            "message": message
                        })
        
        # Trim to requested limit
        logs = logs[-limit:]
        
        # Return the logs in reverse order (oldest first)
        logs.reverse()
        
        return {
            "success": True,
            "logs": logs
        }
    except Exception as e:
        frappe.log(f"Error retrieving AI email logs: {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving logs: {str(e)}",
            "logs": []
        }

@frappe.whitelist()
def get_lead_structure(lead_name):
    """Get the complete structure of a lead document for debugging purposes"""
    try:
        # Get the lead document
        lead = frappe.get_doc("CRM Lead", lead_name)
        
        # Convert to dictionary
        lead_dict = lead.as_dict()
        
        # Remove large or sensitive fields
        fields_to_exclude = [
            "amended_from", "docstatus", "parent", "parentfield", 
            "parenttype", "idx", "owner", "creation", "modified", 
            "modified_by", "_user_tags", "__islocal", "__unsaved"
        ]
        
        for field in fields_to_exclude:
            if field in lead_dict:
                del lead_dict[field]
        
        # Log the fields for debugging
        log(f"Lead structure request for: {lead_name}", "info")
        log(f"Available fields: {', '.join(lead_dict.keys())}", "info")
        
        return {
            "success": True,
            "lead": lead_dict
        }
    except Exception as e:
        log(f"Error getting lead structure: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error getting lead structure: {str(e)}"
        }

@frappe.whitelist()
def debug_failed_job(job_id):
    """Debug a failed job by retrieving its error details"""
    try:
        # Import required modules
        from rq import Queue
        from rq.job import Job
        from frappe.utils.background_jobs import get_redis_conn
        import traceback
        
        log(f"Debugging job with ID: {job_id}", "info")
        
        # Get Redis connection
        conn = get_redis_conn()
        
        # Try to fetch the job by ID
        job = None
        try:
            job = Job.fetch(job_id, connection=conn)
            log(f"Job fetched with ID: {job_id}", "info")
        except Exception as e:
            log(f"Error fetching job: {str(e)}", "error")
            
            # Try alternative formats
            if "||" in job_id:
                simple_id = job_id.split("||")[1]
                try:
                    job = Job.fetch(simple_id, connection=conn)
                    log(f"Job fetched with simple ID: {simple_id}", "info")
                except Exception as e2:
                    log(f"Error fetching with simple ID: {str(e2)}", "error")
        
        if not job:
            return {
                "success": False,
                "message": "Job not found in Redis"
            }
        
        # Get job status
        status = job.get_status()
        log(f"Job status: {status}", "info")
        
        # Get exception info if job failed
        error_details = None
        if status == "failed":
            try:
                # First try the deprecated exc_info for compatibility
                error_details = job.exc_info
                log(f"Got error details using exc_info: {bool(error_details)}", "info")
                
                # If not available, try latest_result()
                if not error_details:
                    result = job.latest_result()
                    if isinstance(result, Exception):
                        error_details = str(result)
                    log(f"Got error details using latest_result: {bool(error_details)}", "info")
            except Exception as e:
                log(f"Error getting exception info: {str(e)}", "error")
        
        # Get job metadata
        meta_keys = [
            f"crm:bulk_email:job:{job_id}",
            f"bulk_email_job_{job_id}"
        ]
        
        if "||" in job_id:
            simple_id = job_id.split("||")[1]
            meta_keys.extend([
                f"crm:bulk_email:job:{simple_id}",
                f"bulk_email_job_{simple_id}"
            ])
        
        job_meta = None
        for key in meta_keys:
            try:
                meta = frappe.cache().get_value(key)
                if meta:
                    job_meta = meta
                    log(f"Found job metadata with key: {key}", "info")
                    break
            except Exception as e:
                log(f"Error getting job metadata with key {key}: {str(e)}", "error")
        
        # Return detailed job information
        return {
            "success": True,
            "job_id": job_id,
            "status": status,
            "created_at": str(job.created_at) if hasattr(job, 'created_at') else None,
            "started_at": str(job.started_at) if hasattr(job, 'started_at') else None,
            "ended_at": str(job.ended_at) if hasattr(job, 'ended_at') else None,
            "error_message": error_details,
            "function": job.func_name if hasattr(job, 'func_name') else None,
            "args": str(job.args) if hasattr(job, 'args') else None,
            "kwargs": str(job.kwargs) if hasattr(job, 'kwargs') else None,
            "meta": job_meta
        }
    except Exception as e:
        log(f"Error debugging job: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error debugging job: {str(e)}"
        } 