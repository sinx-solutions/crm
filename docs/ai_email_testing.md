# AI Email Generator Testing Guide

This guide provides step-by-step instructions for testing the AI Email Generator feature in Frappe CRM.

## Prerequisites

1. Configure the OpenAI API key:
   - Edit `frappe-bench/sites/common_site_config.json`
   - Remove the `_` prefix from `_openai_api_key` and add your actual key

2. Restart the bench server:
   ```bash
   bench restart
   ```

## Testing Individual Email Generation

1. **Navigate to a Lead**:
   - Go to CRM > Leads
   - Click on any lead to open the lead details page

2. **Open Email Composer**:
   - Click on the "Activities" tab
   - Click "Email" to open the email composer

3. **Generate AI Email**:
   - In the email composer toolbar, click the "AI" button
   - Select a tone (Professional, Friendly, Formal, or Persuasive)
   - Add any additional context (optional)
   - Click "Generate Email"

4. **Verify Generated Email**:
   - Check that the generated email is personalized to the lead
   - Contains relevant information about products based on the lead's industry/role
   - Has appropriate tone as selected

5. **Test Email Sending**:
   - Click "Send Test" to send a test email to the configured email address (sanchayt@sinxsolutions.ai)
   - Check the test email in your inbox
   - Verify the formatting and content is correct

6. **Apply to Email**:
   - Click "Use This" to apply the generated content to your email composer
   - Verify that the subject and content are correctly added to the composer
   - Make any additional edits if needed

## Testing Bulk Email Generation

1. **Select Multiple Leads**:
   - Go to CRM > Leads
   - Select several leads by checking the boxes next to them

2. **Open Bulk AI Email Generator**:
   - Click the three dots (more options) in the selection banner
   - Select "Generate AI Emails" from the dropdown

3. **Configure Bulk Generation**:
   - Select a tone for all emails
   - Add any additional context (optional)
   - Keep "Test Mode" enabled for testing
   - Click "Generate Emails"

4. **Monitor Progress**:
   - Check the success message once the bulk job is initiated
   - Watch the terminal logs for processing details
   - Check the dedicated log file at `frappe-bench/logs/ai_email.log`

5. **Verify Test Emails**:
   - Check the test email inbox (sanchayt@sinxsolutions.ai)
   - Verify that emails were generated for all selected leads
   - Confirm each email is personalized to the specific lead

## Debugging

If you encounter issues:

1. **Check Logs**:
   - Main log file: `frappe-bench/logs/ai_email.log`
   - Terminal output during the process
   - Browser console for frontend errors

2. **Common Issues**:
   - API key not configured correctly
   - Permission issues with the test email address
   - Rate limiting from OpenAI API
   - Missing lead data needed for personalization

3. **Error Messages**:
   - The system provides detailed error messages that should help diagnose problems
   - Look for specific error codes if OpenAI API fails

## Next Steps

After successful testing, you can:

1. Disable test mode for bulk emails to send to actual lead email addresses
2. Fine-tune the prompts if needed (in the `ai_email.py` file)
3. Extend the functionality to other doctypes like Deals or Contacts

## Helpful Commands

```bash
# View logs in real-time
tail -f frappe-bench/logs/ai_email.log

# Check the Frappe error log
tail -f frappe-bench/logs/frappe.log

# Restart the bench after making changes
bench restart
``` 