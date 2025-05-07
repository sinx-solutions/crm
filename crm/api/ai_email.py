import frappe
import json
import logging
import os
from frappe import _
from frappe.utils import now_datetime, get_formatted_email
import requests
from frappe.utils.background_jobs import enqueue
from dotenv import load_dotenv
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
            load_dotenv(env_path)
            
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
    """Generate email content for a lead using AI"""
    # Initialize environment if needed
    init_environment()
    
    log(f"Generating email for lead: {lead_name}", "info")
    
    try:
        # Get the lead data
        lead = frappe.get_doc("CRM Lead", lead_name)
        log(f"Lead data retrieved: {lead.first_name} {lead.last_name}", "debug")
        
        # Get all fields as dictionary
        lead_fields = lead.as_dict()
        
        # Remove any large or unnecessary fields
        fields_to_exclude = ["amended_from", "docstatus", "parent", "parentfield", 
                            "parenttype", "idx", "owner", "creation", "modified", 
                            "modified_by", "doctype", "_user_tags", "__islocal"]
        
        for field in fields_to_exclude:
            if field in lead_fields:
                del lead_fields[field]
        
        log(f"Lead fields prepared for AI context. Fields: {', '.join(lead_fields.keys())}", "debug")
        
        # Get API key from environment variables
        openrouter_key = os.getenv("OPENROUTER_KEY")
        
        if not openrouter_key:
            log("OpenRouter API key not found in .env file", "error")
            return {
                "success": False,
                "message": "OpenRouter API key not configured. Please add it to .env file."
            }
        
        # Construct prompt for the AI
        prompt = construct_prompt(lead_fields, tone, additional_context)
        log("Prompt constructed for AI", "debug")
        
        # Call OpenRouter API (using GPT-4o)
        response = call_openrouter_api(prompt, openrouter_key)
        log("Received response from OpenRouter API", "debug")
        
        if not response["success"]:
            return response
        
        # For testing, always send to test email
        log("Returning generated content to frontend", "info")
        
        return {
            "success": True,
            "subject": response["subject"],
            "content": response["content"],
            "debug_info": {
                "lead_name": lead.lead_name,
                "tone": tone
            }
        }
        
    except Exception as e:
        log(f"Error generating email content: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error generating email: {str(e)}"
        }

def construct_prompt(lead_fields, tone, additional_context):
    """Construct the prompt for OpenAI API"""
    
    # Basic lead info
    lead_name = f"{lead_fields.get('first_name', '')} {lead_fields.get('last_name', '')}".strip()
    organization = lead_fields.get('organization', 'their organization')
    email = lead_fields.get('email', '')
    job_title = lead_fields.get('job_title', 'professional')
    industry = lead_fields.get('industry', '')
    
    # Get current user (sender) information
    sender_info = {}
    try:
        user = frappe.get_doc("User", frappe.session.user)
        sender_info = {
            "name": user.full_name,
            "email": user.email,
            "designation": user.designation or "Solutions Consultant",
            "phone": user.phone or ""
        }
    except Exception as e:
        frappe.log(f"AI Email DEBUG: Error getting sender info: {str(e)}")
        sender_info = {
            "name": "Sinx Team",
            "email": "info@sinxsolutions.ai",
            "designation": "Solutions Consultant",
            "phone": ""
        }
    
    # Product context
    product_context = """
    Sinx Solutions offers: 
    - BUNDLR: AI-powered product bundling to maximize cart value
    - PERSONALIZR: Real-time persona generation for precise marketing
    - CATALOGR: Intelligent product categorization for better navigation
    - REPORTR: Auto-generated visual insights for quick decision-making
    - RECOMMENDR: Context-aware product recommendations
    - AI CONSULTANCY: Custom AI solution development
    - MY CAREER GROWTH: AI-driven personalized career guidance
    - KNOWTICE: Real-time, AI-curated industry notifications
    """
    
    # Tone guidelines
    tone_guidelines = {
        "professional": "Write in a clear, formal, and professional manner appropriate for business communication.",
        "friendly": "Write in a warm, approachable tone while maintaining professionalism.",
        "formal": "Write in a highly formal, somewhat conservative tone suitable for traditional industries.",
        "persuasive": "Write in a compelling, benefit-focused tone that encourages action."
    }
    
    # Convert lead_fields to JSON using custom encoder for datetime objects
    lead_fields_json = json.dumps(lead_fields, indent=2, cls=CustomJSONEncoder)
    
    prompt = f"""
    You are writing a highly personalized email from {sender_info['name']} ({sender_info['designation']} at Sinx Solutions) to {lead_name} who works at {organization} as a {job_title} in the {industry} industry.

    Lead Information:
    {lead_fields_json}
    
    Product Information:
    {product_context}
    
    Instructions:
    1. Create a personalized email that connects Sinx Solutions' products SPECIFICALLY to the lead's industry, role, company size, and other relevant attributes.
    2. ONLY suggest 2-3 products that are MOST relevant to this specific lead based on their data - don't mention all products.
    3. Explain specifically how those selected products would solve challenges common in their industry or role.
    4. Include specific, data-driven reasons why these solutions would benefit them - not generic benefits.
    5. DO NOT include ANY placeholder text like [Your Name] or [Your Position] - use the actual sender information provided.
    6. Start the email body directly with your introduction and value proposition.
    7. The email should be concise (200-300 words), direct, and focus on value proposition.
    8. Include your full signature details (name, title, email, phone) at the end of the email.
    9. {tone_guidelines.get(tone, tone_guidelines["professional"])}

    Additional Context/Instructions:
    {additional_context}
    
    Format your response as JSON with a 'subject' field and 'content' field.
    The 'content' should be formatted as HTML with appropriate paragraph tags.
    """
    
    return prompt

def call_openrouter_api(prompt, api_key):
    """Generate personalized email content using OpenRouter AI."""
    log("Calling OpenRouter API (model: openai/gpt-4o)", "debug")
    
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        # Optional headers for OpenRouter
        headers = {
            "HTTP-Referer": "https://sinxsolutions.ai", 
            "X-Title": "Sinx CRM - AI Email Generator"
        }
        
        completion = client.chat.completions.create(
            extra_headers=headers,
            model="openai/gpt-4o",  # Using GPT-4o
            messages=[
                {"role": "system", "content": "You are an expert email copywriter who specializes in creating personalized business emails."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        content = completion.choices[0].message.content
        log(f"Received response from OpenRouter", "debug")
        
        # Parse JSON response
        content_json = json.loads(content)
        
        return {
            "success": True,
            "subject": content_json.get("subject", "Introduction from Sinx Solutions"),
            "content": content_json.get("content", "<p>Error parsing AI response.</p>")
        }
        
    except Exception as e:
        log(f"Error calling OpenRouter API: {str(e)}", "error")
        return {
            "success": False,
            "message": f"Error calling OpenRouter API: {str(e)}"
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
def generate_bulk_emails(filter_json=None, tone="professional", additional_context="", test_mode=1):
    """Generate AI emails for leads based on filters
    
    Args:
        filter_json (str, optional): JSON string of filters. Defaults to None.
        tone (str, optional): Email tone. Defaults to "professional".
        additional_context (str, optional): Additional context for AI. Defaults to "".
        test_mode (int, optional): Send to test email only. Defaults to 1.
    
    Returns:
        dict: Response with job ID
    """
    # Initialize environment
    init_environment()
    
    log(f"Starting bulk email generation with tone: {tone}", "info")
    
    # DEBUGGING: Print all incoming parameters
    print("\n==== BULK EMAIL DEBUG ====")
    print(f"RECEIVED PARAMETERS:")
    print(f"filter_json: {filter_json}")
    print(f"tone: {tone}")
    print(f"additional_context: {additional_context}")
    print(f"test_mode: {test_mode}")
    print(f"test_mode type: {type(test_mode)}")
    
    # Add detailed logging to file
    log(f"RECEIVED PARAMETERS IN API:", "info")
    log(f"filter_json: {filter_json}", "info")
    log(f"tone: {tone}", "info")
    log(f"additional_context: {additional_context}", "info")
    log(f"test_mode: {test_mode} (type: {type(test_mode)})", "info")
    
    # Convert test_mode to actual boolean if it's a string
    if isinstance(test_mode, str):
        test_mode = test_mode.lower() == 'true'
        print(f"Converted test_mode to: {test_mode}")
        log(f"Converted test_mode to: {test_mode}", "info")
    
    try:
        # Parse filters if provided
        filters = {}
        if filter_json:
            try:
                filters = json.loads(filter_json)
                log(f"Using filters: {filters}", "debug")
                print(f"DEBUG - Parsed filters: {filters}")
            except json.JSONDecodeError as e:
                log(f"Error parsing filter JSON: {str(e)}", "error")
                print(f"DEBUG - Error parsing filter JSON: {str(e)}")
                return {
                    "success": False,
                    "message": f"Invalid filter format: {str(e)}"
                }
        else:
            log("No filters provided, will fetch all leads", "info")
            print("DEBUG - No filters provided, will fetch all leads")
        
        # Get leads matching the filters
        try:
            log(f"Querying CRM Lead with filters: {filters}", "debug")
            print(f"DEBUG - Querying CRM Lead with filters: {filters}")
            leads = frappe.get_list("CRM Lead", 
                                filters=filters,
                                fields=["name", "email", "first_name", "last_name", "organization", "industry", "job_title", "source", "status"],
                                limit_page_length=100)  # Limit for safety
            print(f"DEBUG - Query returned {len(leads)} leads")
            print(f"DEBUG - First few leads: {leads[:5] if leads else 'None'}")
            
            # Log complete lead details to file
            log(f"Query returned {len(leads)} leads", "info")
            for i, lead in enumerate(leads):
                log(f"Lead {i+1}: {json.dumps(lead, indent=2, cls=CustomJSONEncoder)}", "info")
            
            # For debugging, store lead information in a system setting
            try:
                # Create temporary storage for leads data for debugging
                frappe.cache().set_value("last_bulk_email_leads", json.dumps(leads, cls=CustomJSONEncoder), expires_in_sec=3600)
                log("Cached leads data for debugging", "info")
            except Exception as cache_err:
                log(f"Warning: Could not cache leads data: {str(cache_err)}", "warning")
                
        except Exception as e:
            log(f"Database error when fetching leads: {str(e)}", "error") 
            print(f"DEBUG - Database error: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching leads: {str(e)}"
            }
        
        lead_count = len(leads)
        log(f"Found {lead_count} leads matching the filters", "info")
        print(f"DEBUG - Found {lead_count} leads matching the filters")
        
        if lead_count == 0:
            # Provide more detailed error message
            filter_details = json.dumps(filters, indent=2)
            log(f"No leads found with filters: {filter_details}", "error")
            print(f"DEBUG - No leads found with filters: {filter_details}")
            return {
                "success": False,
                "message": f"No leads found matching the filters. Please check your selection or filters.\n\nFilter details: {filter_details}"
            }
        
        # Start background job for processing - IMPORTANT: We use the job.id from RQ now
        print(f"DEBUG - Starting background job for {lead_count} leads with tone: {tone}, test_mode: {test_mode}")
        job = enqueue(
            process_bulk_emails,
            queue="long",
            timeout=3600,  # 1 hour timeout
            leads=leads,
            tone=tone,
            additional_context=additional_context,
            test_mode=test_mode
        )
        
        # Use the job ID provided by RQ
        job_id = job.id
        print(f"DEBUG - RQ job created with ID: {job_id}")
        log(f"RQ job created with ID: {job_id}", "info")
        
        # Create job tracking document with the RQ job ID
        job_data = {
            "job_id": job_id,
            "leads_count": lead_count,
            "status": "queued",
            "progress": 0,
            "timestamp": now_datetime(),
            "tone": tone,
            "test_mode": test_mode,
            "user": frappe.session.user,
            "processed_leads": [],
            "successful_leads": [],
            "failed_leads": [],
            "log_entries": []
        }
        
        # Store job metadata in Redis with TTL of 24 hours
        job_meta_key = f"crm:bulk_email:job:{job_id}"
        frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
        log(f"Job data stored in Redis with key: {job_meta_key}", "info")
        
        # Store job data in cache (legacy method) with the RQ job ID
        frappe.cache().set_value(f"bulk_email_job_{job_id}", json.dumps(job_data, cls=CustomJSONEncoder), expires_in_sec=3600)
        
        response = {
            "success": True,
            "message": f"Bulk email generation started for {lead_count} leads. Check the logs for progress.",
            "job_id": job_id
        }
        print(f"DEBUG - Returning response: {response}")
        print("==== END BULK EMAIL DEBUG ====\n")
        return response
        
    except Exception as e:
        log(f"Error initiating bulk email generation: {str(e)}", "error")
        log(f"Error traceback: {frappe.get_traceback()}", "error")
        print(f"DEBUG - Error: {str(e)}")
        print(f"DEBUG - Traceback: {frappe.get_traceback()}")
        return {
            "success": False,
            "message": f"Error initiating bulk email generation: {str(e)}"
        }

def process_bulk_emails(leads, tone, additional_context, test_mode=True, **kwargs):
    """Process the bulk email generation job
    
    This function is executed in a background job.
    It updates the job status in Redis at each step.
    
    Args:
        leads (list): List of lead documents
        tone (str): Email tone (professional, friendly, etc.)
        additional_context (str): Additional instructions for AI
        test_mode (bool): If True, emails will only be sent to test email
        **kwargs: Additional arguments (for backward compatibility)
    """
    # Initialize environment first (critical for background jobs)
    init_environment()
    
    # Get the current job ID from RQ
    from rq import get_current_job
    current_job = get_current_job()
    job_id = current_job.id if current_job else None
    
    if not job_id:
        log("WARNING: No job ID found in RQ context. This shouldn't happen.", "error")
        # Create a fallback job ID just in case
        job_id = frappe.generate_hash(length=10)
    
    # For debugging, log the full job ID format
    log(f"RQ Job ID: {job_id}", "debug")
    
    # Extract the simple ID without site prefix if present
    simple_job_id = job_id.split("||")[1] if "||" in job_id else job_id
    
    # Create both key formats
    job_meta_key = f"crm:bulk_email:job:{job_id}"
    simple_meta_key = f"crm:bulk_email:job:{simple_job_id}"
    
    # Setup logging with job ID for tracking
    job_log = lambda msg, level="info": log(f"[Job {simple_job_id}] {msg}", level)
    
    job_log(f"Starting bulk email generation for {len(leads)} leads (job_id: {job_id})", "info")
    
    try:
        # Get job data from Redis (try both key formats)
        job_data = frappe.cache().get_value(job_meta_key)
        
        # If not found with full key, try the simple key
        if not job_data and job_id != simple_job_id:
            job_data = frappe.cache().get_value(simple_meta_key)
            job_log(f"Job data found with simple key: {simple_meta_key}", "debug")
        
        if not job_data:
            job_log("Job data not found in Redis, creating new", "warning")
            job_data = {
                "job_id": job_id,
                "simple_job_id": simple_job_id,  # Store both formats for reference
                "leads_count": len(leads),
                "status": "running",
                "progress": 0,
                "successful_leads_details": [],
                "failed_leads_details": [],
                "timestamp": now_datetime()
            }
        
        # Update job status to running
        job_data["status"] = "running"
        
        # Store with both key formats for maximum compatibility
        frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
        
        # Also store with simple key if different
        if job_id != simple_job_id:
            frappe.cache().set_value(simple_meta_key, job_data, expires_in_sec=86400)
            job_log(f"Stored job data with both full and simple keys", "debug")
                
        # Get cache from traditional method too for backward compatibility
        old_job_data_json = frappe.cache().get_value(f"bulk_email_job_{job_id}")
        if not old_job_data_json:
            old_job_data_json = frappe.cache().get_value(f"bulk_email_job_{simple_job_id}")
            
        if old_job_data_json:
            try:
                old_job_data = json.loads(old_job_data_json)
                old_job_data["status"] = "running"
                frappe.cache().set_value(f"bulk_email_job_{job_id}", 
                                     json.dumps(old_job_data, cls=CustomJSONEncoder), 
                                     expires_in_sec=3600)
                
                # Also store with simple key
                frappe.cache().set_value(f"bulk_email_job_{simple_job_id}", 
                                     json.dumps(old_job_data, cls=CustomJSONEncoder), 
                                     expires_in_sec=3600)
            except Exception as e:
                job_log(f"Error updating old job data: {str(e)}", "error")
                
        # Process each lead
        successful_leads_details = job_data.get("successful_leads_details", []) # Start with existing if resuming
        failed_leads_details = job_data.get("failed_leads_details", [])
        
        total_leads = len(leads)
        for i, lead_info in enumerate(leads):
            lead_name = lead_info.get("name")
            if not lead_name:
                job_log(f"Skipping lead at index {i} due to missing name", "warning")
                continue # Skip this iteration
                
            try:
                job_log(f"Processing lead {i+1}/{total_leads}: {lead_name}", "info")
                
                # Update progress in Redis
                progress = int(((i + 1) / total_leads) * 100)
                job_data["progress"] = progress
                frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
                
                # Broadcast progress update via websocket
                try:
                    frappe.publish_realtime(
                        "bulk_email_progress", 
                        {"lead": lead_name, "progress": progress, "status": "processing", "job_id": job_id}
                    )
                except Exception as e:
                    job_log(f"Error sending realtime update: {str(e)}", "error")
                
                # Process this lead - Use the modified function
                result = generate_email_for_lead(lead_name, tone, additional_context, test_mode)
                
                # Record detailed success/failure
                if result.get("generation_successful"):
                    lead_detail = {
                        "name": lead_name, 
                        "communication_id": result.get("communication_id")
                    }
                    if result.get("sending_successful"):
                        job_log(f"Successfully generated and sent email for lead {lead_name}", "info")
                        successful_leads_details.append(lead_detail)
                        # Send realtime update for success
                        try:
                            frappe.publish_realtime(
                                "bulk_email_progress", 
                                {"lead": lead_name, "progress": progress, "status": "success", "job_id": job_id}
                            )
                        except Exception as e:
                            job_log(f"Error sending realtime success update: {str(e)}", "error")
                    else:
                        job_log(f"Generated communication for {lead_name} but failed to send email: {result.get('message')}", "error")
                        lead_detail["error"] = f"Send failed: {result.get('message')}"
                        failed_leads_details.append(lead_detail)
                        # Send realtime update for error
                        try:
                            frappe.publish_realtime(
                                "bulk_email_progress", 
                                {"lead": lead_name, "progress": progress, "status": "error", "job_id": job_id, "error": result.get("message")}
                            )
                        except Exception as e:
                            job_log(f"Error sending realtime error update: {str(e)}", "error")
                else:
                    job_log(f"Failed to generate email/communication for lead {lead_name}: {result.get('message')}", "error")
                    failed_leads_details.append({
                        "name": lead_name, 
                        "error": f"Generation failed: {result.get('message')}"
                    })
                    # Send realtime update for error
                    try:
                        frappe.publish_realtime(
                            "bulk_email_progress", 
                            {"lead": lead_name, "progress": progress, "status": "error", "job_id": job_id, "error": result.get("message")}
                        )
                    except Exception as e:
                        job_log(f"Error sending realtime error update: {str(e)}", "error")

                # Update job data in Redis with detailed lists immediately after processing
                job_data["successful_leads_details"] = successful_leads_details
                job_data["failed_leads_details"] = failed_leads_details
                frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
                
                time.sleep(0.5) # Add delay
                
            except Exception as e:
                # Catch unexpected errors during the loop iteration
                job_log(f"CRITICAL LOOP ERROR processing lead {lead_name}: {str(e)}", "error")
                job_log(f"ERROR TRACEBACK (loop): {frappe.get_traceback()}", "error")
                failed_leads_details.append({"name": lead_name, "error": f"Loop error: {str(e)}"})
                # Update job data in Redis immediately
                job_data["failed_leads_details"] = failed_leads_details
                frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
                
        # Update final job status in Redis
        job_data["status"] = "completed" if not failed_leads_details else "completed_with_errors"
        job_data["progress"] = 100
        job_data["completed_at"] = now_datetime()
        frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
        
        # Final log
        success_count = len(successful_leads_details)
        fail_count = len(failed_leads_details)
        job_log(f"Bulk email job completed. Emails Sent Successfully: {success_count}, Failures (Generation or Send): {fail_count}", "info")
        
        # Broadcast completion
        try:
            frappe.publish_realtime(
                "bulk_email_complete", 
                {
                    "job_id": job_id, 
                    "status": job_data["status"],
                    "successful_count": success_count, 
                    "failed_count": fail_count,
                    "processed_details": successful_leads_details + failed_leads_details # Send combined list
                }
            )
        except Exception as e:
            job_log(f"Error sending completion notification: {str(e)}", "error")
            
        return {
            "success": fail_count == 0,
            "message": f"Processed {total_leads} leads. Success: {success_count}, Failed: {fail_count}",
            "details": {
                "successful": successful_leads_details,
                "failed": failed_leads_details
            }
        }
        
    except Exception as e:
        # Handle errors in the whole job execution
        job_log(f"Critical error in bulk email job execution: {str(e)}", "error")
        job_log(f"Error traceback: {frappe.get_traceback()}", "error")
        
        # Update job status to error if job_data was initialized
        if job_data:
            try:
                job_data["status"] = "error"
                job_data["error"] = str(e)
                job_data["error_at"] = now_datetime()
                frappe.cache().set_value(job_meta_key, job_data, expires_in_sec=86400)
            except Exception as e2:
                job_log(f"Error updating job status to error: {str(e2)}", "error")
                
        # Try to broadcast error
        try:
            frappe.publish_realtime(
                "bulk_email_error", 
                {"job_id": job_id, "error": str(e)}
            )
        except Exception as e2:
            job_log(f"Error sending error notification: {str(e2)}", "error")
            
        # Ensure the RQ job itself is marked as failed by re-raising
        raise e

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
def send_ai_email(recipients, subject, content, doctype="CRM Lead", name=None, cc=None, bcc=None, force_resend=False):
    """Send an email using Frappe's email system but keeping the AI-generated content and HTML template"""
    log(f"==== BACKEND: AI EMAIL SENDING STARTED ====", "info")
    log(f"DETAILS: Recipients={recipients}, Subject={subject}, DocType={doctype}, Name={name}", "info")
    
    try:
        # Get current user information
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
        
        # Get recipient first name if doctype and name provided
        recipient_name = "there"
        if doctype == "CRM Lead" and name:
            try:
                lead = frappe.get_doc(doctype, name)
                recipient_name = lead.first_name or "there"
                log(f"BACKEND: Found lead with first_name: {recipient_name}", "info")
                
                # Update subject if needed
                if not subject or subject == "Email from Lead":
                    lead_prefix = lead.lead_name or lead.organization or ""
                    if lead_prefix:
                        subject = f"{lead_prefix} ({lead.name})"
                    else:
                        subject = f"Regarding Lead {lead.name}"
                    log(f"BACKEND: Updated subject to: {subject}", "info")
            except Exception as e:
                log(f"BACKEND: Error fetching lead: {str(e)}", "error")
        
        # Format email addresses
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
        
        log(f"BACKEND: Parsed recipients={recipient_list}, cc={cc_list}, bcc={bcc_list}", "info")
        
        # Create email template and wrap content in it
        html_template = get_email_template(subject)
        # Use the correct placeholders defined in get_email_template
        rendered_html = html_template.replace("__AI_EMAIL_BODY_CONTENT__", content)
        rendered_html = rendered_html.replace("__SENDER_FULL_NAME__", sender_name)
        # Note: The template doesn't have a placeholder for recipient_name like "{ name }" was attempting before.

        log("BACKEND: Email template applied to content", "info")
        
        # Convert recipients to comma-separated string for Frappe's sendmail
        recipients_str = ", ".join(recipient_list) if isinstance(recipient_list, list) else recipient_list
        cc_str = ", ".join(cc_list) if isinstance(cc_list, list) and cc_list else ""
        bcc_str = ", ".join(bcc_list) if isinstance(bcc_list, list) and bcc_list else ""
        
        # Convert HTML to text
        try:
            from frappe.utils.html_utils import html2text
        except ImportError:
            try:
                from frappe.utils.html import html2text
            except ImportError:
                # Simple fallback if html2text is not available
                import re
                def html2text(html_content):
                    text = re.sub(r'<[^>]*>', ' ', html_content)
                    return re.sub(r'\s+', ' ', text).strip()
        
        # Create Communication doc first
        log("BACKEND: Creating communication record directly", "info")
        communication = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "sent_or_received": "Sent",
            "email_status": "Open",
            "subject": subject,
            "content": rendered_html,
            "text_content": html2text(rendered_html),
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
        
        # Insert the communication doc
        communication.flags.ignore_permissions = True
        communication.flags.ignore_mandatory = True
        communication.insert()
        log(f"BACKEND: Communication created with ID: {communication.name}", "info")
        
        # Create Communication Link to ensure it shows up in the timeline
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
            
        # Now send the actual email using Frappe's sendmail
        log("BACKEND: Sending email via Frappe's sendmail", "info")
        frappe.sendmail(
            recipients=recipients_str,
            sender=sender,
            subject=subject,
            message=rendered_html,
            communication=communication.name,  # Link to the communication doc
            reference_doctype=doctype,
            reference_name=name,
            cc=cc_str,
            bcc=bcc_str,
            now=True,  # Send immediately
            expose_recipients="header"  # Show all recipients in the email
        )
        
        # Force commit changes to database to ensure they're visible right away
        frappe.db.commit()
        log(f"BACKEND: Email sent successfully and committed to database", "info")
        
        return {
            "success": True,
            "message": f"Email sent to {recipients}",
            "communication": communication.name
        }
        
    except Exception as e:
        log(f"==== BACKEND ERROR: {str(e)} ====", "error")
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

def generate_email_for_lead(lead_name, tone="professional", additional_context="", test_mode=True):
    """Generate an AI email for a single lead and attempt to send it.
    
    Args:
        lead_name (str): Lead name/ID
        tone (str, optional): Email tone. Defaults to "professional".
        additional_context (str, optional): Additional context for AI. Defaults to "".
        test_mode (bool, optional): If True, email will be sent to the default outgoing address. Defaults to True.
        
    Returns:
        dict: Result indicating success/failure of generation AND sending attempt.
    """
    generation_successful = False
    sending_successful = False
    communication_id = None
    error_message = None
    subject = "AI Email Generation Failed" # Default subject
    ai_generated_body = "<p>There was an error generating the AI email content.</p>" # Default body content

    try:
        log(f"BEGIN: Generating email for lead: {lead_name}", "info")
        
        # 1. Get Lead Data
        lead = frappe.get_doc("CRM Lead", lead_name)
        lead_fields = lead.as_dict()
        
        # 2. Generate AI Content
        log(f"Starting AI content generation for {lead_name}", "debug")
        try:
            # Prepare lead fields for prompt
            fields_to_exclude = [
                "amended_from", "docstatus", "parent", "parentfield", 
                "parenttype", "idx", "owner", "creation", "modified", 
                "modified_by", "doctype", "_user_tags", "__islocal", "__unsaved"
            ]
            prepared_lead_fields = lead_fields.copy()
            for field in fields_to_exclude:
                if field in prepared_lead_fields:
                    del prepared_lead_fields[field]
            
            # Construct prompt
            prompt = construct_prompt(prepared_lead_fields, tone, additional_context)
            log(f"Prompt constructed for lead {lead_name}", "debug")

            # Get API key
            openrouter_key = os.getenv("OPENROUTER_KEY")
            if not openrouter_key:
                raise ValueError("OpenRouter API key not found in .env file.")

            # Call AI API
            ai_response = call_openrouter_api(prompt, openrouter_key)
            
            if not ai_response.get("success"):
                raise ValueError(f"AI API call failed: {ai_response.get('message', 'Unknown API error')}")

            # Use generated subject and content BODY
            subject = ai_response.get("subject", f"Follow up regarding {lead.lead_name or lead_name}")
            ai_generated_body = ai_response.get("content", "<p>Error retrieving content from AI response.</p>")
            generation_successful = True
            log(f"AI content generated successfully for lead {lead_name}", "info")

        except Exception as ai_error:
            error_message = f"Error during AI content generation: {str(ai_error)}"
            log(f"ERROR: AI Generation failed for lead {lead_name}. Error: {str(ai_error)}", "error")

        # 3. Prepare Email Sending Details
        # Get recipient email
        recipient_email = lead.email
        if not recipient_email:
            raise ValueError(f"Lead {lead_name} has no email address.")
        
        # Use default outgoing email as recipient in test mode for safety
        default_sender_email = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
        if test_mode:
            if not default_sender_email:
                 raise ValueError("Cannot run in test_mode: No default outgoing email account configured to send test emails to.")
            original_recipient = recipient_email
            recipient_email = default_sender_email 
            log(f"TEST MODE: Overriding recipient to default sender: {recipient_email} (Original: {original_recipient})", "info")
        else:
             log(f"Recipient determined: {recipient_email} (test_mode: {test_mode})", "info")

        # Determine sender 
        sender = get_formatted_email(frappe.session.user or "Administrator")
        sender_name_only = frappe.db.get_value("User", frappe.session.user or "Administrator", "full_name") or "Sinx Solutions"
        log(f"Sender determined: {sender}", "info")

        # Get default outgoing email account name
        default_email_account_name = frappe.db.get_value(
            "Email Account", {"default_outgoing": 1}, "name"
        )
        if not default_email_account_name:
            raise ValueError("No default outgoing email account configured.")
        log(f"Default outgoing email account determined: {default_email_account_name}", "info")
        
        # 3.1 Render Full HTML Email using the template
        log(f"Rendering full HTML email for {lead_name}", "debug")
        full_html_content = render_full_email(
            ai_generated_body=ai_generated_body, 
            lead_data=lead_fields, # Pass the original lead dict
            sender_name=sender_name_only,
            subject=subject
        )
        log(f"Full HTML content rendered. Length: {len(full_html_content)}", "debug")

        # 4. Create Communication Record
        # (Use AI generated subject and FULL RENDERED HTML content)
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "communication_medium": "Email",
            "subject": subject,
            "content": full_html_content, # <--- Use fully rendered HTML
            "text_content": html2text(full_html_content), # Also generate plain text version
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "sender": sender,
            "recipients": recipient_email,
            "email_status": "Open",
            "sent_or_received": "Sent",
            "email_account": default_email_account_name,
            "is_ai_generated": 1 if generation_successful else 0
        })
        comm.insert(ignore_permissions=True)
        communication_id = comm.name
        log(f"Communication record created: {communication_id} (AI Success: {generation_successful})", "info")

        # 5. Attempt to Send Email via Frappe Queue
        try:
            email_args = {
                "recipients": recipient_email,
                "sender": sender,
                "subject": subject,
                "message": full_html_content, # <--- Use fully rendered HTML
                "reference_doctype": "CRM Lead",
                "reference_name": lead.name,
                "communication": communication_id,
                "now": True 
            }
            log(f"ATTEMPTING EMAIL SEND via frappe.sendmail for Comm: {communication_id}", "info")
            log(f"DEBUG: Args for frappe.sendmail: {json.dumps(email_args, default=str)}", "debug")

            frappe.sendmail(**email_args)
            
            frappe.db.commit()

            sending_successful = True
            log(f"SUCCESS: frappe.sendmail completed for Comm: {communication_id}. Email queued.", "info")
            
            frappe.db.set_value("Communication", communication_id, "email_status", "Sent")
            frappe.db.commit() # Commit status update
            log(f"Communication status updated to Sent for {communication_id}", "info")

        except Exception as email_error:
            sending_successful = False
            error_message = f"Error during frappe.sendmail: {str(email_error)}"
            log(f"ERROR: frappe.sendmail failed for Comm: {communication_id}. Error: {str(email_error)}", "error")
            log(f"ERROR TRACEBACK (sendmail): {frappe.get_traceback()}", "error")
            try:
                frappe.db.set_value("Communication", communication_id, "email_status", "Error")
                frappe.db.commit()
                log(f"Communication status updated to Error for {communication_id}", "warning")
            except Exception as db_update_err:
                log(f"ERROR: Could not update communication status to Error for {communication_id}: {str(db_update_err)}", "error")

    except Exception as e:
        # Catch broader errors (e.g., lead fetch, missing email, missing default account)
        if not error_message: # Avoid overwriting specific AI or sendmail errors
             error_message = f"Error during email generation process: {str(e)}"
        log(f"CRITICAL ERROR: Process failed for lead {lead_name}. Error: {str(e)}", "error")
        log(f"ERROR TRACEBACK (main): {frappe.get_traceback()}", "error")
        generation_successful = generation_successful 
        sending_successful = False 

    # Return detailed status
    final_status = {
        "success": generation_successful and sending_successful, # Overall success requires both
        "message": error_message if error_message else ("Email generated and sent/queued successfully" if generation_successful else "Email generation failed"),
        "generation_successful": generation_successful,
        "sending_successful": sending_successful,
        "communication_id": communication_id
    }
    log(f"END: Result for lead {lead_name}: {json.dumps(final_status, default=str)}", "info")
    return final_status

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
