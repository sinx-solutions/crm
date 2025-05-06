// Simple translation utility function
// Formats strings with placeholders like '{0}', '{1}', etc.

/**
 * Translate and format a string with variables
 * @param {string} text - The text to translate with optional placeholders like '{0}', '{1}'
 * @param {Array} args - An array of values to replace the placeholders
 * @returns {string} - The translated and formatted string
 */
export function __(text, args = []) {
  // For now, we're just implementing the formatting part
  // Later this could connect to Frappe's translation system
  if (!text) return '';
  
  // Format the string with arguments if provided
  if (args && args.length) {
    return text.replace(/{(\d+)}/g, (match, number) => {
      return typeof args[number] !== 'undefined' 
        ? args[number]
        : match;
    });
  }
  
  return text;
}

// Export other translation-related utilities as needed
export const locale = () => 'en'; 