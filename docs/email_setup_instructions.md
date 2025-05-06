# Email System Setup Instructions

## Setting Up Frappe Email

1. Go to **Email Account** in the Frappe settings:
   - Navigate to: `http://newcrm.localhost/app/email-account`
   - Or search for "Email Account" in the search bar

2. Click on **New**

3. Fill in the following details:
   - **Email Address**: Your email address (e.g., youremail@gmail.com)
   - **Email Account Name**: A descriptive name (e.g., "Gmail Outgoing")
   - **Email Account Type**: Select "Outgoing"
   - **Password**: Your email password or app password
   - Check **Enable Outgoing**
   - Set as **Default Outgoing**: Yes
   - **SMTP Server**: Depends on your email provider (e.g., smtp.gmail.com for Gmail)
   - **SMTP Port**: Typically 587 for TLS or 465 for SSL
   - **Use TLS**: Yes (recommended)
   
4. Click **Save**

> **Note for Gmail Users**: You may need to use an "App Password" instead of your regular password. Go to your Google Account > Security > 2-Step Verification > App passwords to generate one.

## Setting Up Resend

1. Create a `.env` file in the CRM app directory if it doesn't exist:
   ```bash
   cd frappe-bench/apps/crm
   touch .env
   ```

2. Add the following to the `.env` file:
   ```
   RESEND_API_KEY=your_resend_api_key
   RESEND_DEFAULT_FROM=your_verified_sending_email@example.com
   OPENROUTER_KEY=your_openrouter_key
   SENDER_NAME="Your Name"
   ```

3. Restart the Frappe server:
   ```bash
   bench restart
   ```

## Testing the Toggle

1. After setting up both email systems, open the Lead form and click on the **Reply** button

2. In the email editor, you should see a toggle in the toolbar showing either "Resend" or "Frappe"

3. Click on the refresh icon next to it to switch between the two email services

4. When you send an email, it will use the currently selected service

## Troubleshooting

### If the toggle doesn't appear:
- Make sure both email systems are properly configured
- Check the browser console for any errors
- Refresh the page to reload the preferences

### If you get errors when sending:
- For Frappe email: Check that your SMTP settings are correct
- For Resend: Verify that your API key is valid and the sending email is verified
- Check the server logs for more detailed error information:
  ```bash
  bench logs
  ```

### To manually check/set preferences:
```python
# To get current preference
frappe.db.get_single_value("System Settings", "crm_email_sending_service")

# To set preference
frappe.db.set_value("System Settings", "System Settings", "crm_email_sending_service", "resend")  # or "frappe"
frappe.db.commit()
``` 