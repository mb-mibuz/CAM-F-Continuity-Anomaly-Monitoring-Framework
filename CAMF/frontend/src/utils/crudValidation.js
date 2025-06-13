/**
 * CRUD Validation Utilities
 * 
 * Ensures data consistency and validation for all CRUD operations
 */

import { handleError } from '../services/ErrorHandler';

// Validation rules for different entity types
const validationRules = {
  project: {
    name: {
      required: true,
      minLength: 1,
      maxLength: 255,
      pattern: /^[a-zA-Z0-9\s\-_]+$/,
      message: 'Project name must contain only letters, numbers, spaces, hyphens, and underscores'
    }
  },
  
  scene: {
    name: {
      required: true,
      minLength: 1,
      maxLength: 255,
      pattern: /^[a-zA-Z0-9\s\-_]+$/,
      message: 'Scene name must contain only letters, numbers, spaces, hyphens, and underscores'
    },
    project_id: {
      required: true,
      type: 'number'
    }
  },
  
  angle: {
    name: {
      required: true,
      minLength: 1,
      maxLength: 255,
      pattern: /^[a-zA-Z0-9\s\-_#]+$/,
      message: 'Angle name must contain only letters, numbers, spaces, hyphens, underscores, and #'
    },
    scene_id: {
      required: true,
      type: 'number'
    }
  },
  
  take: {
    name: {
      required: true,
      minLength: 1,
      maxLength: 255,
      pattern: /^[a-zA-Z0-9\s\-_#]+$/,
      message: 'Take name must contain only letters, numbers, spaces, hyphens, underscores, and #'
    },
    angle_id: {
      required: true,
      type: 'number'
    },
    is_reference: {
      type: 'boolean'
    }
  },
  
  note: {
    content: {
      required: true,
      minLength: 1,
      maxLength: 5000
    },
    take_id: {
      required: true,
      type: 'number'
    },
    frame_number: {
      type: 'number',
      min: 0
    }
  }
};

/**
 * Validate entity data against rules
 */
export function validateEntity(entityType, data) {
  const rules = validationRules[entityType];
  if (!rules) {
    throw new Error(`Unknown entity type: ${entityType}`);
  }
  
  const errors = {};
  
  for (const [field, rule] of Object.entries(rules)) {
    const value = data[field];
    
    // Check required
    if (rule.required && (value === undefined || value === null || value === '')) {
      errors[field] = `${field} is required`;
      continue;
    }
    
    // Skip further validation if not required and empty
    if (!rule.required && (value === undefined || value === null || value === '')) {
      continue;
    }
    
    // Type validation
    if (rule.type && typeof value !== rule.type) {
      errors[field] = `${field} must be a ${rule.type}`;
      continue;
    }
    
    // String validations
    if (typeof value === 'string') {
      if (rule.minLength && value.length < rule.minLength) {
        errors[field] = `${field} must be at least ${rule.minLength} characters`;
      }
      
      if (rule.maxLength && value.length > rule.maxLength) {
        errors[field] = `${field} must be at most ${rule.maxLength} characters`;
      }
      
      if (rule.pattern && !rule.pattern.test(value)) {
        errors[field] = rule.message || `${field} has invalid format`;
      }
    }
    
    // Number validations
    if (typeof value === 'number') {
      if (rule.min !== undefined && value < rule.min) {
        errors[field] = `${field} must be at least ${rule.min}`;
      }
      
      if (rule.max !== undefined && value > rule.max) {
        errors[field] = `${field} must be at most ${rule.max}`;
      }
    }
  }
  
  return {
    isValid: Object.keys(errors).length === 0,
    errors
  };
}

/**
 * Sanitize entity data
 */
export function sanitizeEntity(entityType, data) {
  const sanitized = { ...data };
  
  // Trim string fields
  for (const [key, value] of Object.entries(sanitized)) {
    if (typeof value === 'string') {
      sanitized[key] = value.trim();
    }
  }
  
  // Remove undefined fields
  for (const key of Object.keys(sanitized)) {
    if (sanitized[key] === undefined) {
      delete sanitized[key];
    }
  }
  
  return sanitized;
}

/**
 * Validate and prepare entity for API
 */
export function prepareEntityForAPI(entityType, data) {
  // Sanitize first
  const sanitized = sanitizeEntity(entityType, data);
  
  // Validate
  const validation = validateEntity(entityType, sanitized);
  
  if (!validation.isValid) {
    const error = new Error('Validation failed');
    error.validationErrors = validation.errors;
    throw error;
  }
  
  return sanitized;
}

/**
 * Check for duplicate names within scope
 */
export function checkDuplicateName(items, newName, excludeId = null) {
  const normalizedNewName = newName.trim().toLowerCase();
  
  return items.some(item => {
    if (excludeId && item.id === excludeId) {
      return false;
    }
    
    const normalizedItemName = (item.name || '').trim().toLowerCase();
    return normalizedItemName === normalizedNewName;
  });
}

/**
 * Generate unique name if duplicate exists
 */
export function generateUniqueName(baseName, existingNames) {
  let name = baseName;
  let counter = 1;
  
  const normalizedExisting = existingNames.map(n => n.toLowerCase());
  
  while (normalizedExisting.includes(name.toLowerCase())) {
    counter++;
    name = `${baseName} ${counter}`;
  }
  
  return name;
}

/**
 * Validate parent-child relationships
 */
export function validateRelationship(parentType, parentId, childType) {
  const validRelationships = {
    project: ['scene'],
    scene: ['angle'],
    angle: ['take'],
    take: ['frame', 'note']
  };
  
  const allowedChildren = validRelationships[parentType];
  if (!allowedChildren || !allowedChildren.includes(childType)) {
    throw new Error(`Invalid relationship: ${parentType} cannot have ${childType} as child`);
  }
  
  if (!parentId || typeof parentId !== 'number') {
    throw new Error(`Invalid ${parentType} ID`);
  }
  
  return true;
}

/**
 * Create operation wrapper with validation
 */
export function createWithValidation(entityType, createFn) {
  return async (data) => {
    try {
      const prepared = prepareEntityForAPI(entityType, data);
      const result = await createFn(prepared);
      return result;
    } catch (error) {
      handleError(error, `Create ${entityType}`, data);
      throw error;
    }
  };
}

/**
 * Update operation wrapper with validation
 */
export function updateWithValidation(entityType, updateFn) {
  return async (id, data) => {
    try {
      const prepared = prepareEntityForAPI(entityType, data);
      const result = await updateFn(id, prepared);
      return result;
    } catch (error) {
      handleError(error, `Update ${entityType}`, { id, data });
      throw error;
    }
  };
}

/**
 * Delete operation wrapper with confirmation
 */
export function deleteWithConfirmation(entityType, deleteFn, confirmFn) {
  return async (id, options = {}) => {
    try {
      if (options.skipConfirmation !== true && confirmFn) {
        const confirmed = await confirmFn({
          title: `Delete ${entityType}?`,
          message: `Are you sure you want to delete this ${entityType}? This action cannot be undone.`,
          confirmText: 'Delete',
          cancelText: 'Cancel',
          type: 'danger'
        });
        
        if (!confirmed) {
          return false;
        }
      }
      
      const result = await deleteFn(id);
      return result;
    } catch (error) {
      handleError(error, `Delete ${entityType}`, { id });
      throw error;
    }
  };
}