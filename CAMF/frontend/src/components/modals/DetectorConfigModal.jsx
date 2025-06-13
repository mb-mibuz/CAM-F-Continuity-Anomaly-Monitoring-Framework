import React, { useState, useEffect } from 'react';
import ModalBase from './ModalBase';
import { useDetectors, useDetectorSchema, useSceneDetectorConfigs, useSaveDetectorConfig } from '../../queries/hooks';
import { useAppStore } from '../../stores';
import { DetectorService } from '../../services';
import { api } from '../../utils/api';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../queries/keys';

export default function DetectorConfigModal({ 
  sceneName, 
  sceneConfig,
  sceneId = null,
  editMode = false,
  onBack, 
  onCreate, 
  onClose,
  onSuccess
}) {
  const [selectedDetector, setSelectedDetector] = useState(null);
  const [detectorConfigs, setDetectorConfigs] = useState({});
  const [enabledDetectors, setEnabledDetectors] = useState([]);
  const [schemas, setSchemas] = useState({});
  
  const { addNotification } = useAppStore();
  const detectorService = DetectorService.getInstance();
  const queryClient = useQueryClient();
  
  // Use React Query hooks
  const { data: detectorsRaw, isLoading: loadingDetectors, error } = useDetectors();
  const { data: sceneConfigs, isLoading: loadingConfigs } = useSceneDetectorConfigs(
    sceneId, 
    { enabled: editMode && !!sceneId }
  );
  const saveConfigMutation = useSaveDetectorConfig();
  
  // Filter out invalid detectors (ones that might be in config but not on disk)
  const detectors = React.useMemo(() => {
    if (!detectorsRaw) return [];
    
    // Filter out any detectors that have invalid names or are missing required properties
    return detectorsRaw.filter(detector => {
      // Must have a name
      if (!detector.name) return false;
      
      // Should have version (indicates valid detector.json)
      if (!detector.version) {
        console.warn(`Detector ${detector.name} missing version, likely invalid`);
        return false;
      }
      
      return true;
    });
  }, [detectorsRaw]);
  
  // Initialize configs when scene configs load
  useEffect(() => {
    if (sceneConfigs && detectors) {
      const settings = sceneConfigs.detector_settings || sceneConfigs.configs || sceneConfigs.configurations || {};
      const enabled = sceneConfigs.enabled_detectors || sceneConfigs.enabledDetectors || [];
      console.log('[DetectorConfigModal] Loading scene configs:', sceneConfigs);
      console.log('[DetectorConfigModal] Detector settings:', settings);
      console.log('[DetectorConfigModal] Enabled detectors:', enabled);
      console.log('[DetectorConfigModal] Edit mode:', editMode);
      console.log('[DetectorConfigModal] Scene ID:', sceneId);
      
      // Filter out enabled detectors that no longer exist
      const validDetectorNames = detectors.map(d => d.name);
      const validEnabled = enabled.filter(name => validDetectorNames.includes(name));
      
      if (validEnabled.length < enabled.length) {
        console.warn('[DetectorConfigModal] Removed non-existent detectors from enabled list:', 
          enabled.filter(name => !validDetectorNames.includes(name))
        );
      }
      
      setEnabledDetectors(validEnabled);
      
      // Only keep configs for valid detectors
      const validSettings = {};
      for (const [name, config] of Object.entries(settings)) {
        if (validDetectorNames.includes(name)) {
          validSettings[name] = config;
        }
      }
      setDetectorConfigs(validSettings);
    }
  }, [sceneConfigs, detectors]);
  
  // Select first detector by default
  useEffect(() => {
    if (detectors && detectors.length > 0 && !selectedDetector) {
      setSelectedDetector(detectors[0].name);
    }
  }, [detectors, selectedDetector]);
  
  // Load all detector schemas
  useEffect(() => {
    if (detectors && detectors.length > 0) {
      // In edit mode, wait for scene configs to load first
      if (editMode && !sceneConfigs) {
        return;
      }
      loadAllSchemas();
    }
  }, [detectors, editMode, sceneConfigs]);
  
  const loadAllSchemas = async () => {
    const newSchemas = {};
    
    for (const detector of detectors) {
      try {
        // Use name (registry key) for API calls
        const response = await detectorService.getDetectorSchema(detector.name);
        
        // Extract schema from response
        const schema = response.schema || response;
        newSchemas[detector.name] = schema;
        
        // Only initialize config with defaults if we haven't loaded configs from the API yet
        // This prevents overwriting saved configs with defaults
        setDetectorConfigs(prev => {
          if (!prev[detector.name]) {
            // No existing config, so initialize with defaults
            const initialConfig = {};
            if (schema.fields) {
              Object.entries(schema.fields).forEach(([fieldName, field]) => {
                if (field.default !== undefined) {
                  initialConfig[fieldName] = field.default;
                }
              });
            }
            return {
              ...prev,
              [detector.name]: initialConfig
            };
          }
          // Already have config, don't overwrite
          return prev;
        });
      } catch (error) {
        console.error(`Failed to load schema for ${detector.display_name || detector.name}:`, error);
      }
    }
    
    setSchemas(newSchemas);
  };
  
  const handleToggleDetector = async (detectorName) => {
    const wasEnabled = enabledDetectors.includes(detectorName);
    
    setEnabledDetectors(prev => {
      if (prev.includes(detectorName)) {
        return prev.filter(d => d !== detectorName);
      } else {
        // When enabling a detector, ensure it has config with defaults
        const schema = schemas[detectorName];
        if (schema && !detectorConfigs[detectorName]) {
          const defaultConfig = {};
          if (schema.fields) {
            Object.entries(schema.fields).forEach(([fieldName, field]) => {
              if (field.default !== undefined) {
                defaultConfig[fieldName] = field.default;
              }
            });
          }
          setDetectorConfigs(prev => ({
            ...prev,
            [detectorName]: defaultConfig
          }));
        }
        return [...prev, detectorName];
      }
    });
    
    // If in edit mode (scene already exists), start/stop detector immediately
    if (editMode && sceneId) {
      try {
        if (!wasEnabled) {
          // Start the detector
          console.log(`[DetectorConfigModal] Starting detector ${detectorName} for scene ${sceneId}`);
          const config = detectorConfigs[detectorName] || {};
          await api.startDetector(detectorName, { scene_id: sceneId, config });
          addNotification({ 
            type: 'success', 
            message: `${detectorName} started successfully` 
          });
        } else {
          // Stop the detector
          console.log(`[DetectorConfigModal] Stopping detector ${detectorName}`);
          await api.stopDetector(detectorName);
          addNotification({ 
            type: 'success', 
            message: `${detectorName} stopped successfully` 
          });
        }
      } catch (error) {
        console.error(`Failed to ${wasEnabled ? 'stop' : 'start'} detector:`, error);
        addNotification({ 
          type: 'error', 
          message: `Failed to ${wasEnabled ? 'stop' : 'start'} ${detectorName}` 
        });
        // Revert the toggle on error
        setEnabledDetectors(prev => 
          wasEnabled ? [...prev, detectorName] : prev.filter(d => d !== detectorName)
        );
      }
    }
  };
  
  const handleConfigChange = async (detectorName, fieldName, value) => {
    setDetectorConfigs(prev => ({
      ...prev,
      [detectorName]: {
        ...prev[detectorName],
        [fieldName]: value
      }
    }));
    
    // If in edit mode and detector is enabled, update its config immediately
    if (editMode && sceneId && enabledDetectors.includes(detectorName)) {
      try {
        console.log(`[DetectorConfigModal] Updating config for ${detectorName}:`, { [fieldName]: value });
        const newConfig = {
          ...detectorConfigs[detectorName],
          [fieldName]: value
        };
        // Update the detector's configuration
        await api.updateDetectorConfig(sceneId, detectorName, newConfig);
      } catch (error) {
        console.error(`Failed to update detector config:`, error);
        // Don't show notification for every field change
      }
    }
  };
  
  const validateConfigs = () => {
    for (const detectorName of enabledDetectors) {
      const schema = schemas[detectorName];
      const config = detectorConfigs[detectorName] || {};
      
      if (!schema?.fields) continue;
      
      for (const [fieldName, field] of Object.entries(schema.fields)) {
        if (field.required && !config[fieldName]) {
          return {
            valid: false,
            error: `${detectorName} requires "${field.title || fieldName}" to be configured`
          };
        }
      }
    }
    
    return { valid: true };
  };
  
  const handleCreate = async () => {
    const validation = validateConfigs();
    
    if (!validation.valid) {
      // For now, just show error and return
      // TODO: Implement confirm dialog
      addNotification({ 
        type: 'warning', 
        message: validation.error 
      });
      return;
    }
    
    // Build configs for ALL enabled detectors
    const allConfigs = {};
    
    for (const detectorName of enabledDetectors) {
      const config = detectorConfigs[detectorName] || {};
      const schema = schemas[detectorName];
      
      // Build complete config with defaults
      const completeConfig = {};
      
      if (schema?.fields) {
        for (const [fieldName, field] of Object.entries(schema.fields)) {
          // Use the configured value, or fall back to default
          if (config[fieldName] !== undefined && config[fieldName] !== '') {
            completeConfig[fieldName] = config[fieldName];
          } else if (field.default !== undefined) {
            completeConfig[fieldName] = field.default;
          }
        }
      }
      
      // Always include the config, even if not all required fields are present
      allConfigs[detectorName] = completeConfig;
    }
    
    // For creation mode, only include valid configs
    const finalConfigs = {};
    const finalEnabled = [];
    
    if (!editMode) {
      // Only include detectors with valid configs for creation
      for (const detectorName of enabledDetectors) {
        const config = allConfigs[detectorName];
        const schema = schemas[detectorName];
        
        let isValid = true;
        if (schema?.fields) {
          for (const [fieldName, field] of Object.entries(schema.fields)) {
            if (field.required && !config[fieldName]) {
              isValid = false;
              break;
            }
          }
        }
        
        if (isValid) {
          finalEnabled.push(detectorName);
          finalConfigs[detectorName] = config;
        }
      }
    } else {
      // In edit mode, save all configs
      finalEnabled.push(...enabledDetectors);
      Object.assign(finalConfigs, allConfigs);
    }
    
    if (editMode) {
      try {
        console.log('[DetectorConfigModal] Saving detector config:', {
          sceneId,
          enabled_detectors: finalEnabled,
          detector_settings: finalConfigs
        });
        
        // Update the scene with enabled detectors and their configurations
        const updateResponse = await api.updateScene(sceneId, {
          enabled_detectors: finalEnabled,
          detector_settings: finalConfigs
        });
        
        console.log('[DetectorConfigModal] Update response:', updateResponse);
        
        // Invalidate the cache to ensure we get fresh data
        await queryClient.invalidateQueries({ 
          queryKey: queryKeys.scenes.detectorConfigs(sceneId) 
        });
        await queryClient.invalidateQueries({ 
          queryKey: queryKeys.scenes.detail(sceneId) 
        });
        
        // Show success notification
        addNotification({ 
          type: 'success', 
          message: 'Detector configuration saved successfully' 
        });
        
        // Call success callback if provided
        if (onSuccess) {
          onSuccess();
        }
        
        // Close modal - use onClose for edit mode, onCreate for create mode
        if (onClose) {
          onClose();
        } else if (onCreate) {
          onCreate();
        }
      } catch (error) {
        console.error('Failed to save detector config:', error);
        if (error && error.response?.data?.detail) {
          const detail = error.response.data.detail;
          if (typeof detail === 'object' && detail.errors) {
            addNotification({ type: 'error', message: `Configuration errors: ${detail.errors.join(', ')}` });
          } else if (typeof detail === 'string') {
            addNotification({ type: 'error', message: `Failed to save: ${detail}` });
          } else {
            addNotification({ type: 'error', message: `Failed to save: ${JSON.stringify(detail)}` });
          }
        } else if (error && error.message) {
          addNotification({ type: 'error', message: `Failed to save: ${error.message}` });
        } else {
          addNotification({ type: 'error', message: 'Failed to save detector configurations' });
        }
      }
    } else {
      onCreate(finalEnabled, finalConfigs);
    }
  };
  
  const renderConfigField = (detectorName, fieldName, field) => {
    const value = detectorConfigs[detectorName]?.[fieldName] ?? field.default ?? '';
    const fieldType = field.field_type || field.type;
    
    switch (fieldType) {
      case 'text':
        if (field.options?.length > 0) {
          return (
            <select
              value={value}
              onChange={(e) => handleConfigChange(detectorName, fieldName, e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:border-black"
            >
              <option value="">Select {field.title}</option>
              {field.options.map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          );
        }
        return (
          <input
            type="text"
            value={value}
            onChange={(e) => handleConfigChange(detectorName, fieldName, e.target.value)}
            placeholder={field.description}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:border-black"
          />
        );
      
      case 'number':
      case 'slider':
        const min = field.minimum || field.min || 0;
        const max = field.maximum || field.max || 1;
        const progress = ((value - min) / (max - min)) * 100;
        
        return (
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="relative flex items-center h-5">
                <div 
                  className="absolute inset-x-0 h-0.5 rounded-full"
                  style={{
                    background: `linear-gradient(to right, #515151 0%, #515151 ${progress}%, #D1D5DB ${progress}%, #D1D5DB 100%)`
                  }}
                />
                <input
                  type="range"
                  value={value}
                  onChange={(e) => handleConfigChange(detectorName, fieldName, parseFloat(e.target.value))}
                  min={min}
                  max={max}
                  step={field.step || (max - min) / 100 || 0.01}
                  className="relative w-full appearance-none bg-transparent cursor-pointer z-10"
                />
              </div>
            </div>
            <span className="text-14 text-gray-600 font-medium w-12 text-right">
              {typeof value === 'number' ? value.toFixed(2) : value}
            </span>
          </div>
        );
      
      case 'boolean':
      case 'checkbox':
        return (
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={value || false}
              onChange={(e) => handleConfigChange(detectorName, fieldName, e.target.checked)}
              className="w-4 h-4 accent-black"
            />
            <span className="text-14">{field.description}</span>
          </label>
        );
      
      case 'select':
        return (
          <select
            value={value}
            onChange={(e) => handleConfigChange(detectorName, fieldName, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:border-black"
          >
            {!field.required && <option value="">Select {field.title}</option>}
            {(field.options || []).map(option => (
              <option key={option.value || option} value={option.value || option}>
                {option.label || option}
              </option>
            ))}
          </select>
        );
      
      case 'file':
        return (
          <input
            type="file"
            onChange={(e) => {
              const file = e.target.files[0];
              if (file) {
                handleConfigChange(detectorName, fieldName, file.name);
              }
            }}
            accept={field.accept_extensions?.join(',') || '*'}
            className="text-14"
          />
        );
      
      default:
        return <div className="text-gray-500">Unsupported field type: {fieldType}</div>;
    }
  };
  
  if (loadingDetectors || loadingConfigs) {
    return (
      <ModalBase onClose={onClose} size="large">
        <div className="p-8 h-[400px] flex items-center justify-center">
          <p className="text-16 text-gray-500">Loading detectors...</p>
        </div>
      </ModalBase>
    );
  }
  
  if (error) {
    return (
      <ModalBase onClose={onClose} size="large">
        <div className="p-8">
          <h2 className="text-18 font-semibold mb-6">
            {editMode ? 'Detector Configuration' : `Detector Configuration for "${sceneName}"`}
          </h2>
          <div className="text-red-600 mb-4">{error.message}</div>
          <button 
            onClick={() => window.location.reload()} 
            className="px-4 py-2 bg-primary text-white rounded"
          >
            Retry
          </button>
        </div>
      </ModalBase>
    );
  }
  
  return (
    <ModalBase onClose={onClose} size="large">
      <div className="p-8 h-[700px] flex flex-col">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-18 font-semibold truncate max-w-[600px]" title={editMode ? 'Detector Configuration' : `Detector Configuration for "${sceneName}"`}>
            {editMode ? 'Detector Configuration' : `Detector Configuration for "${sceneName}"`}
          </h2>
          {!editMode && onBack && (
            <button
              onClick={onBack}
              className="text-14 text-gray-600 hover:text-black"
            >
              ← Back
            </button>
          )}
        </div>
        
        <div className="flex flex-1 gap-6 min-h-0">
          {/* Left sidebar - detector list */}
          <div className="w-64 border-r border-gray-200 pr-4 overflow-y-auto">
            <h3 className="text-14 font-medium mb-3">Available Detectors</h3>
            {!detectors || detectors.length === 0 ? (
              <p className="text-14 text-gray-500">No detectors installed</p>
            ) : (
              <div className="space-y-2">
                {detectors.map(detector => (
                  <button
                    key={detector.name}
                    onClick={() => setSelectedDetector(detector.name)}
                    className={`w-full text-left p-3 rounded border transition-colors ${
                      selectedDetector === detector.name
                        ? 'bg-gray-100 border-black'
                        : 'border-gray-200 hover:border-gray-400'
                    } ${
                      enabledDetectors.includes(detector.name)
                        ? 'border-l-4 border-l-green-500'
                        : ''
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-14 font-medium truncate">{detector.display_name || detector.name}</span>
                      {enabledDetectors.includes(detector.name) && (
                        <span className="text-12 text-green-600">ON</span>
                      )}
                    </div>
                    <p className="text-12 text-gray-600 mt-1">{detector.version}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Right side - detector details */}
          <div className="flex-1 overflow-y-auto">
            {selectedDetector && schemas[selectedDetector] ? (
              <div>
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-16 font-medium">
                      {detectors.find(d => d.name === selectedDetector)?.display_name || selectedDetector}
                    </h3>
                    <button
                      onClick={() => handleToggleDetector(selectedDetector)}
                      className={`px-4 py-2 rounded text-14 font-medium ${
                        enabledDetectors.includes(selectedDetector)
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-300 text-gray-700'
                      }`}
                    >
                      {enabledDetectors.includes(selectedDetector) ? 'ON' : 'OFF'}
                    </button>
                  </div>
                  {/* Show detector description if available */}
                  {detectors.find(d => d.name === selectedDetector)?.description && (
                    <p className="text-14 text-gray-600 mb-4">
                      {detectors.find(d => d.name === selectedDetector).description}
                    </p>
                  )}
                </div>
                
                {!enabledDetectors.includes(selectedDetector) ? (
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-14 text-gray-600">
                      Turn ON this detector to configure its settings.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <h4 className="text-14 font-medium">Configuration</h4>
                    {!schemas[selectedDetector].fields || Object.entries(schemas[selectedDetector].fields).length === 0 ? (
                      <p className="text-14 text-gray-500">No configuration required</p>
                    ) : (
                      Object.entries(schemas[selectedDetector].fields).map(([fieldName, field]) => (
                        <div key={fieldName}>
                          <label className="block text-14 font-medium mb-2">
                            {field.title || fieldName}
                            {field.required && <span className="text-red-500 ml-1">*</span>}
                          </label>
                          {renderConfigField(selectedDetector, fieldName, field)}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full">
                <p className="text-14 text-gray-500">
                  {!detectors || detectors.length === 0 
                    ? 'No detectors available'
                    : 'Select a detector to configure'}
                </p>
              </div>
            )}
          </div>
        </div>
        
        <div className="flex justify-end gap-3 mt-6 pt-6 border-t">
          <button 
            onClick={onClose}
            className="px-4 py-2 text-14 font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
          <button 
            onClick={handleCreate}
            disabled={saveConfigMutation.isLoading}
            className="px-4 py-2 text-14 font-medium text-white bg-primary rounded hover:opacity-80 disabled:opacity-50"
          >
            {saveConfigMutation.isLoading ? 'Saving...' : (editMode ? 'Save' : 'Create')}
          </button>
        </div>
      </div>
    </ModalBase>
  );
}