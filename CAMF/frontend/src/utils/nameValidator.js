// src/utils/nameValidator.js

/**
 * Validate a name for filesystem safety
 * @param {string} name - The name to validate
 * @returns {object} - { isValid: boolean, error: string }
 */
export function validateName(name) {
  if (!name || !name.trim()) {
    return { isValid: false, error: "Name cannot be empty" };
  }

  const trimmedName = name.trim();

  if (trimmedName.length > 200) {
    return { isValid: false, error: "Name is too long (maximum 200 characters)" };
  }

  // Check for forbidden characters
  const forbiddenChars = '<>:"|?*/\\';
  const foundForbidden = [...forbiddenChars].find(char => trimmedName.includes(char));
  if (foundForbidden) {
    return { isValid: false, error: `Name cannot contain: ${forbiddenChars}` };
  }

  // Check for control characters
  if ([...trimmedName].some(char => char.charCodeAt(0) < 32)) {
    return { isValid: false, error: "Name contains invalid control characters" };
  }

  // Check for reserved Windows names
  const reservedNames = [
    'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
    'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
    'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
  ];

  const upperName = trimmedName.toUpperCase();
  const baseName = upperName.split('.')[0];
  if (reservedNames.includes(upperName) || reservedNames.includes(baseName)) {
    return { isValid: false, error: `'${trimmedName}' is a reserved system name` };
  }

  // Check for leading/trailing dots
  if (trimmedName.startsWith('.') || trimmedName.endsWith('.')) {
    return { isValid: false, error: "Name cannot start or end with dots" };
  }

  // Check if the name has actual content after removing spaces
  if (trimmedName.replace(/\s+/g, '').length === 0) {
    return { isValid: false, error: "Name must contain actual characters" };
  }

  return { isValid: true, error: "" };
}

/**
 * Sanitize a name for display (doesn't make it filesystem safe, just cleans it)
 * @param {string} name - The name to sanitize
 * @returns {string} - Sanitized name
 */
export function sanitizeName(name) {
  if (!name) return "";
  
  // Trim whitespace
  let sanitized = name.trim();
  
  // Replace multiple spaces with single space
  sanitized = sanitized.replace(/\s+/g, ' ');
  
  return sanitized;
}