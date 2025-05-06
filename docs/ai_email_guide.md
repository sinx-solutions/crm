# AI Email Generator for Frappe CRM

This guide explains how to set up and use the AI Email Generator feature in Frappe CRM, which allows you to create personalized emails for leads using OpenAI's GPT models.

## Setup

### 1. Configure API Keys

Edit the `common_site_config.json` file in your Frappe bench:

```json
{
  // ... existing configuration ...
  
  "openai_api_key": "your_openai_api_key_here",
  "resend_api_key": "your_resend_api_key_here",
  "sender_name": "Your Name or Company"
}
```

> **Note**: The keys in the file are prefixed with an underscore (`_`) by default. Remove the underscore to activate them.

### 2. Restart the Bench

After adding your API keys, restart your Frappe bench:

```bash
bench restart
```

## Using the AI Email Generator

### Single Email Generation

1. Navigate to a lead in CRM
2. Click on the "Activities" tab
3. Click on "Email"
4. In the email composer, click the "AI" button in the toolbar
5. Select the desired tone (Professional, Friendly, Formal, or Persuasive)
6. Add any additional context (optional)
7. Click "Generate Email"
8. Review the generated email
9. Click "Send Test" to send a test to the configured email
10. Click "Use This" to apply the generated content to your email draft
11. Make any final edits before sending

### Features

- **Dynamic Personalization**: The AI uses all lead data, including custom fields, to generate highly personalized emails
- **Multiple Tones**: Choose from different communication styles based on your needs
- **Additional Context**: Provide specific instructions to guide the AI's content generation
- **Test Emails**: Send test emails to review how they look before using them
- **Editing**: Modify the generated content as needed before sending

## Troubleshooting

### Email Generation Fails

If email generation fails, check:

1. The OpenAI API key is correctly added to the config
2. The API key has sufficient credits/quota
3. Check the logs at `frappe-bench/logs/ai_email.log` for detailed error information

### Test Emails Not Received

If test emails are not being received:

1. Check your spam folder
2. Verify the Resend API key is correct
3. Check the Frappe email settings
4. Review the logs for any error messages

## Technical Details

The AI Email Generator uses OpenAI's GPT-4o model to create personalized emails based on lead data. The system:

1. Fetches all lead data, including custom fields
2. Constructs a prompt with lead details, product information, and tone guidelines
3. Calls the OpenAI API to generate personalized content
4. Formats the response as HTML for use in the email editor

Detailed logs are available in `frappe-bench/logs/ai_email.log` for troubleshooting. 