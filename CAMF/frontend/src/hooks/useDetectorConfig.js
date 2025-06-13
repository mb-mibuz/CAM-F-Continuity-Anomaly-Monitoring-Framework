import { useState, useEffect, useCallback } from 'react';
import { useDetectors, useDetectorSchema, useSceneDetectorConfigs, useSaveDetectorConfig } from '../queries/hooks';
import { useAppStore } from '../stores';
import config, { buildApiUrl } from '../config';

/**
 * Hook for managing detector configurations
 * @param {string} sceneId - Scene ID
 * @param {Object} options - Configuration options
 * @returns {Object} Detector configuration state and controls
 */
export function useDetectorConfig(sceneId, options = {}) {
  const {
    onConfigSaved,
    autoLoadSchemas = true
  } = options;
  
  // State
  const [selectedDetector, setSelectedDetector] = useState(null);
  const [detectorConfigs, setDetectorConfigs] = useState({});
  const [enabledDetectors, setEnabledDetectors] = useState([]);
  const [schemas, setSchemas] = useState({});
  const [isLoadingSchemas, setIsLoadingSchemas] = useState(false);
  
  const { addNotification } = useAppStore();
  
  // Queries
  const { data: detectors, isLoading: loadingDetectors } = useDetectors();
  const { data: sceneConfigs, isLoading: loadingConfigs } = useSceneDetectorConfigs(sceneId);
  const saveConfigMutation = useSaveDetectorConfig();
  
  // Initialize configs when scene configs load
  useEffect(() => {
    if (sceneConfigs) {
      setEnabledDetectors(sceneConfigs.enabledDetectors || []);
      setDetectorConfigs(sceneConfigs.configs || {});
    }
  }, [sceneConfigs]);
  
  // Select first detector by default
  useEffect(() => {
    if (detectors && detectors.length > 0 && !selectedDetector) {
      setSelectedDetector(detectors[0].name);
    }
  }, [detectors, selectedDetector]);
  
  // Load all detector schemas
  useEffect(() => {
    if (autoLoadSchemas && detectors && detectors.length > 0) {
      loadAllSchemas();
    }
  }, [detectors, autoLoadSchemas]);
  
  const loadAllSchemas = async () => {
    setIsLoadingSchemas(true);
    const newSchemas = {};
    
    try {
      for (const detector of detectors) {
        try {
          const response = await fetch(buildApiUrl(`api/detectors/${detector.name}/schema`));
          if (response.ok) {
            const data = await response.json();
            newSchemas[detector.name] = data.schema || { fields: {} };
          }
        } catch (error) {
          console.error(`Failed to load schema for ${detector.name}:`, error);
          newSchemas[detector.name] = { fields: {} };
        }
      }
      
      setSchemas(newSchemas);
    } finally {
      setIsLoadingSchemas(false);
    }
  };
  
  // Toggle detector enabled state
  const toggleDetector = useCallback((detectorName) => {
    setEnabledDetectors(prev => {
      if (prev.includes(detectorName)) {
        return prev.filter(d => d !== detectorName);
      } else {
        return [...prev, detectorName];
      }
    });
  }, []);
  
  // Update detector config field
  const updateConfigField = useCallback((detectorName, fieldName, value) => {
    setDetectorConfigs(prev => ({
      ...prev,
      [detectorName]: {
        ...prev[detectorName],
        [fieldName]: value
      }
    }));
  }, []);
  
  // Get config with defaults
  const getDetectorConfig = useCallback((detectorName) => {
    const config = detectorConfigs[detectorName] || {};
    const schema = schemas[detectorName];
    
    if (!schema || !schema.fields) {
      return config;
    }
    
    // Merge with defaults from schema
    const configWithDefaults = { ...config };
    
    Object.entries(schema.fields).forEach(([fieldName, field]) => {
      if (configWithDefaults[fieldName] === undefined && field.default !== undefined) {
        configWithDefaults[fieldName] = field.default;
      }
    });
    
    return configWithDefaults;
  }, [detectorConfigs, schemas]);
  
  // Validate detector config
  const validateDetectorConfig = useCallback((detectorName) => {
    const config = getDetectorConfig(detectorName);
    const schema = schemas[detectorName];
    
    if (!schema || !schema.fields) {
      return { valid: true };
    }
    
    // Check required fields
    for (const [fieldName, field] of Object.entries(schema.fields)) {
      if (field.required && !config[fieldName]) {
        return {
          valid: false,
          error: `${field.title || fieldName} is required`
        };
      }
      
      // Type validation
      if (config[fieldName] !== undefined) {
        switch (field.field_type) {
          case 'number':
            if (typeof config[fieldName] !== 'number') {
              return {
                valid: false,
                error: `${field.title || fieldName} must be a number`
              };
            }
            if (field.minimum !== undefined && config[fieldName] < field.minimum) {
              return {
                valid: false,
                error: `${field.title || fieldName} must be at least ${field.minimum}`
              };
            }
            if (field.maximum !== undefined && config[fieldName] > field.maximum) {
              return {
                valid: false,
                error: `${field.title || fieldName} must be at most ${field.maximum}`
              };
            }
            break;
            
          case 'text':
            if (field.options && !field.options.includes(config[fieldName])) {
              return {
                valid: false,
                error: `${field.title || fieldName} must be one of: ${field.options.join(', ')}`
              };
            }
            break;
        }
      }
    }
    
    return { valid: true };
  }, [getDetectorConfig, schemas]);
  
  // Validate all enabled detectors
  const validateAllConfigs = useCallback(() => {
    for (const detectorName of enabledDetectors) {
      const validation = validateDetectorConfig(detectorName);
      if (!validation.valid) {
        return {
          valid: false,
          error: `${detectorName}: ${validation.error}`
        };
      }
    }
    
    return { valid: true };
  }, [enabledDetectors, validateDetectorConfig]);
  
  // Save configurations
  const saveConfigurations = useCallback(async () => {
    const validation = validateAllConfigs();
    
    if (!validation.valid) {
      addNotification({ type: 'error', message: validation.error });
      return false;
    }
    
    try {
      // Update scene with enabled detectors
      await fetch(buildApiUrl(`api/scenes/${sceneId}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled_detectors: enabledDetectors })
      });
      
      // Save each detector config
      for (const detectorName of enabledDetectors) {
        const config = getDetectorConfig(detectorName);
        await saveConfigMutation.mutateAsync({
          sceneId,
          detectorName,
          config
        });
      }
      
      addNotification({ type: 'success', message: 'Detector configurations saved' });
      onConfigSaved?.();
      return true;
      
    } catch (error) {
      console.error('Error saving configurations:', error);
      addNotification({ type: 'error', message: 'Failed to save detector configurations' });
      return false;
    }
  }, [sceneId, enabledDetectors, getDetectorConfig, validateAllConfigs, saveConfigMutation, addNotification, onConfigSaved]);
  
  // Reset configurations
  const resetConfigurations = useCallback(() => {
    setDetectorConfigs({});
    setEnabledDetectors([]);
  }, []);
  
  // Import/Export configurations
  const exportConfigurations = useCallback(() => {
    return {
      enabledDetectors,
      detectorConfigs
    };
  }, [enabledDetectors, detectorConfigs]);
  
  const importConfigurations = useCallback((data) => {
    if (data.enabledDetectors) {
      setEnabledDetectors(data.enabledDetectors);
    }
    if (data.detectorConfigs) {
      setDetectorConfigs(data.detectorConfigs);
    }
  }, []);
  
  return {
    // State
    detectors: detectors || [],
    selectedDetector,
    detectorConfigs,
    enabledDetectors,
    schemas,
    
    // Loading states
    isLoading: loadingDetectors || loadingConfigs || isLoadingSchemas,
    isSaving: saveConfigMutation.isLoading,
    
    // Actions
    setSelectedDetector,
    toggleDetector,
    updateConfigField,
    saveConfigurations,
    resetConfigurations,
    
    // Utilities
    getDetectorConfig,
    validateDetectorConfig,
    validateAllConfigs,
    exportConfigurations,
    importConfigurations,
    
    // Computed
    isDetectorEnabled: (name) => enabledDetectors.includes(name),
    hasEnabledDetectors: enabledDetectors.length > 0,
    canSave: enabledDetectors.length > 0 && !saveConfigMutation.isLoading
  };
}