import React, { useEffect } from 'react';
import { useDataStore } from '../../stores';
import { usePolling } from '../../hooks/usePolling';
import config, { buildApiUrl } from '../../config';

/**
 * Manages preview fetching separate from display
 */
export default function PreviewManager({ enabled = true }) {
  const source = useDataStore(state => state.source);
  const isCapturing = useDataStore(state => state.isCapturing);
  const hasFrames = useDataStore(state => state.frameCount > 0);
  const { setPreviewActive, updatePreviewFrame, setPreviewError } = useDataStore();
  
  const shouldPreview = source && !isCapturing && !hasFrames && enabled;
  
  useEffect(() => {
    setPreviewActive(shouldPreview);
    
    if (!shouldPreview) {
      updatePreviewFrame(null);
      setPreviewError(null);
    }
  }, [shouldPreview, setPreviewActive, updatePreviewFrame, setPreviewError]);
  
  const fetchPreview = async () => {
    if (!shouldPreview) return;
    
    try {
      let url;
      
      if (source.type === 'camera') {
        url = buildApiUrl(`api/capture/preview/current?quality=50&t=${Date.now()}`);
      } else {
        const apiSourceType = source.type === 'monitor' ? 'screen' : source.type;
        url = buildApiUrl(`api/capture/preview/${apiSourceType}/${source.id}?quality=50&t=${Date.now()}`);
      }
      
      const response = await fetch(url, {
        headers: {
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data?.frame) {
          updatePreviewFrame(`data:image/jpeg;base64,${data.frame}`);
          setPreviewError(null);
        }
      } else {
        throw new Error(`Preview unavailable (${response.status})`);
      }
    } catch (error) {
      console.error('Preview fetch error:', error);
      setPreviewError(error.message);
    }
  };
  
  // Use polling hook for clean interval management
  usePolling(
    fetchPreview,
    source?.type === 'camera' ? 200 : 100,
    shouldPreview,
    [source?.id, source?.type]
  );
  
  return null; // This component only manages state
}
