import { useState, useEffect, useCallback } from 'react';
import { api } from '../../../utils/api';
import { useAppStore } from '../../../stores';

export function useMonitoringState(takeId, sceneId, angleId) {
  const [state, setState] = useState({
    sceneData: null,
    takeData: null,
    availableTakes: [],
    loading: true,
    error: null
  });

  const { addNotification } = useAppStore();

  // Load all necessary data
  const loadData = useCallback(async () => {
    if (!takeId || !sceneId || !angleId) return;

    try {
      setState(prev => ({ ...prev, loading: true, error: null }));

      // Load in parallel
      const [sceneResponse, takeResponse, anglesResponse] = await Promise.all([
        api.getScene(sceneId),
        api.getTake(takeId),
        api.getAngles(sceneId)
      ]);

      // Get reference take for the angle
      let referenceTakeId = null;
      let referenceFrameCount = 0;
      const currentAngle = anglesResponse.find(a => a.id === angleId);
      console.log('[useMonitoringState] Looking for reference take:', { angleId, currentAngle });
      
      if (currentAngle) {
        try {
          const response = await api.getReferenceTake(angleId);
          console.log('[useMonitoringState] Reference take response:', response);
          if (response && response.reference_take) {
            const refTake = response.reference_take;
            referenceTakeId = refTake.id;
            referenceFrameCount = refTake.frame_count || 0;
            console.log('[useMonitoringState] Found reference take:', { 
              referenceTakeId, 
              referenceFrameCount,
              refTakeName: refTake.name 
            });
          }
        } catch (error) {
          console.log('[useMonitoringState] No reference take found for angle:', angleId, error);
          // No reference take set
        }
      }

      // Load all takes for available angles
      const allTakes = [];
      for (const angle of anglesResponse) {
        try {
          const takes = await api.getTakes(angle.id);
          takes.forEach(take => {
            allTakes.push({
              ...take,
              angleName: angle.name,
              angleId: angle.id,
              isCurrentTake: take.id === takeId,
              isReferenceTake: take.id === referenceTakeId
            });
          });
        } catch (error) {
          console.error(`Error loading takes for angle ${angle.id}:`, error);
        }
      }

      // Update scene data with reference info
      const enrichedSceneData = {
        ...sceneResponse,
        reference_take_id: referenceTakeId,
        reference_frame_count: referenceFrameCount
      };

      console.log('[useMonitoringState] Setting state with reference:', {
        referenceTakeId,
        referenceFrameCount,
        angleId,
        enrichedSceneData
      });

      setState({
        sceneData: enrichedSceneData,
        takeData: takeResponse,
        availableTakes: allTakes,
        loading: false,
        error: null
      });

    } catch (error) {
      console.error('Error loading monitoring data:', error);
      setState(prev => ({
        ...prev,
        loading: false,
        error
      }));
      addNotification({ type: 'error', message: 'Failed to load take data' });
    }
  }, [takeId, sceneId, angleId, addNotification]);

  // Initial load
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Refresh function
  const refreshData = useCallback(async () => {
    await loadData();
  }, [loadData]);

  return {
    ...state,
    refreshData
  };
}