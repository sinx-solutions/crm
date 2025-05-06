// Paste this into your browser's console to debug email toggle issues

(async function debugEmailToggle() {
  console.log("=== Email Toggle Debug Script ===");
  
  // Step 1: Check if EmailEditor component is loaded
  console.log("\n📋 Step 1: Checking EmailEditor component...");
  const app = document.querySelector('.__vue_app__');
  if (!app) {
    console.error("⛔ Vue app not found!");
    return;
  }
  
  // Step 2: Check backend settings
  console.log("\n📋 Step 2: Checking backend settings...");
  try {
    const result = await frappe.call({
      method: 'crm.api.test_email_settings.debug_email_ui',
      args: {}
    });
    
    console.log("Backend settings:", result.message);
    
    if (!result.message.ui_should_show_toggle) {
      console.warn("⚠️ Toggle requirements not met!");
      console.log("- Frappe email configured:", result.message.email_systems.frappe_configured);
      console.log("- Resend configured:", result.message.email_systems.resend_configured);
    } else {
      console.log("✅ Backend says toggle should be shown");
    }
  } catch (error) {
    console.error("⛔ Error checking backend settings:", error);
  }
  
  // Step 3: Force refresh email preferences
  console.log("\n📋 Step 3: Trying to force load email preferences...");
  try {
    const result = await frappe.call({
      method: 'crm.api.ai_email.get_email_preference',
      args: {}
    });
    
    console.log("Email preferences:", result.message);
  } catch (error) {
    console.error("⛔ Error loading email preferences:", error);
  }
  
  // Step 4: Find the EmailEditor component instance
  console.log("\n📋 Step 4: Looking for EmailEditor component...");
  let found = false;
  
  // Open email composer if not already open
  const replyButton = document.querySelector('button[aria-label="Reply"]');
  if (replyButton) {
    console.log("Found reply button, clicking it...");
    replyButton.click();
    // Give it a moment to open
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  // Try to find the component
  const editorElements = document.querySelectorAll('.ProseMirror');
  console.log(`Found ${editorElements.length} editor elements`);
  
  if (editorElements.length > 0) {
    console.log("✅ Email composer is open");
    
    // Check for toggle elements
    const badgeElements = document.querySelectorAll('.badge');
    const toggleVisible = Array.from(badgeElements).some(el => 
      el.textContent.includes('Resend') || el.textContent.includes('Frappe')
    );
    
    console.log(`Found ${badgeElements.length} badge elements`);
    console.log("Toggle badge visible:", toggleVisible);
    
    if (!toggleVisible) {
      console.log("Toggle not found, trying to manually check emailServiceOptions...");
      
      // Try to find the vue component
      try {
        // This is a very hacky way to try to find Vue components
        const vueInstance = window.__VUE_DEVTOOLS_GLOBAL_HOOK__?.instances?.find(i => 
          i.name === 'EmailEditor'
        );
        
        if (vueInstance) {
          console.log("Found EmailEditor Vue instance:", vueInstance);
          console.log("emailServiceOptions:", vueInstance.emailServiceOptions);
        } else {
          console.log("EmailEditor Vue instance not found");
        }
      } catch (e) {
        console.log("Error finding Vue instance:", e);
      }
    }
  } else {
    console.warn("⚠️ Email composer not open");
  }
  
  console.log("\n✨ Debug complete - Check the logs above for issues");
})(); 