import { useState, useCallback, useEffect, useRef } from 'react';
import { api } from '../../../../utils/api';
import { FrameService, SSEService } from '../../../../services';

export function useVideoUpload({ angleId, takeName, onUploadComplete }) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentTakeId, setCurrentTakeId] = useState(null);
  const frameService = FrameService.getInstance();
  const uploadCompleteRef = useRef(false);

  // Subscribe to SSE events for upload progress
  useEffect(() => {
    if (!currentTakeId) return;

    const handleUploadEvent = (event) => {
      console.log('[useVideoUpload] Received SSE event:', event);
      
      // Check different possible event structures
      const eventType = event.event_type || event.type || event.event;
      const eventData = event.data || event;
      
      console.log('[useVideoUpload] Event type:', eventType, 'Event data:', eventData);
      
      if (eventData.take_id !== currentTakeId) return;

      switch (eventType) {
        case 'upload_started':
          console.log('Upload started event:', eventData);
          break;
        case 'frame_captured':
          // Update progress during upload as frames are extracted
          if (eventData.frame_count) {
            console.log('[SSE] Frame captured during upload:', eventData.frame_count);
            // Update progress based on frame count (assuming ~30 frames total)
            const estimatedProgress = Math.min((eventData.frame_count / 30) * 100, 95);
            setUploadProgress(estimatedProgress);
          }
          break;
        case 'upload_completed':
          if (!uploadCompleteRef.current) {
            uploadCompleteRef.current = true;
            console.log('Upload completed event:', eventData);
            console.log('Frame count from SSE:', eventData.frame_count);
            setUploadProgress(100);
            
            // Add a small delay to ensure frames are written to disk
            setTimeout(async () => {
              try {
                // Verify frame count from API
                const frameCountResponse = await api.getFrameCount(currentTakeId);
                const actualFrameCount = frameCountResponse || eventData.frame_count;
                console.log('Verified frame count:', actualFrameCount);
                
                // Load first frame
                let firstFrame = null;
                try {
                  firstFrame = await frameService.loadFrame(currentTakeId, 0);
                  console.log('Successfully loaded first frame');
                } catch (error) {
                  console.warn('Could not load first frame:', error);
                }
                
                console.log('Calling onUploadComplete with frameCount:', actualFrameCount);
                onUploadComplete({
                  takeId: currentTakeId,
                  frameCount: actualFrameCount,
                  firstFrame
                });
              } catch (error) {
                console.error('Error verifying frame count:', error);
                // Fallback to SSE data
                onUploadComplete({
                  takeId: currentTakeId,
                  frameCount: eventData.frame_count,
                  firstFrame: null
                });
              }

              setIsUploading(false);
              setUploadProgress(0);
              setCurrentTakeId(null);
            }, 500); // 500ms delay to ensure frames are written
          }
          break;
        case 'upload_error':
          console.error('Upload error event:', eventData);
          setIsUploading(false);
          setUploadProgress(0);
          setCurrentTakeId(null);
          break;
      }
    };

    // Subscribe to the take-specific channel
    const unsubscribe = SSEService.subscribe(`take_${currentTakeId}`, handleUploadEvent);

    return () => {
      unsubscribe();
    };
  }, [currentTakeId, frameService, onUploadComplete]);

  const uploadVideo = useCallback(async (file) => {
    setIsUploading(true);
    setUploadProgress(0);
    uploadCompleteRef.current = false;

    try {
      // Create temporary take for video
      const response = await api.createTake({
        angleId: angleId,
        name: `${takeName}_video_${Date.now()}`
      });
      const videoTakeId = response.id;
      setCurrentTakeId(videoTakeId);

      // Upload video file
      const uploadResponse = await api.uploadVideoFile(videoTakeId, file);
      console.log('Video upload started:', uploadResponse);

      // Also poll for status as backup (in case SSE events fail)
      const pollInterval = setInterval(async () => {
        if (uploadCompleteRef.current) {
          clearInterval(pollInterval);
          return;
        }

        try {
          const status = await api.getCaptureProgress(videoTakeId);
          
          // Estimate progress based on frame count
          if (status.frame_count > 0) {
            // We don't have total frames yet, so show indeterminate progress
            setUploadProgress(Math.min(status.frame_count / 100, 0.95) * 100);
          }

          // Update progress
          if (status.frame_count > 0) {
            console.log('[Polling] Frame count during upload:', status.frame_count);
          }
          
          // Check if upload is complete by seeing if capture is no longer active
          if (!status.is_capturing && status.frame_count > 0 && !uploadCompleteRef.current) {
            uploadCompleteRef.current = true;
            clearInterval(pollInterval);
            setUploadProgress(100);
            
            console.log('[Polling] Upload complete, frame count:', status.frame_count);
            
            // Load first frame
            let firstFrame = null;
            try {
              firstFrame = await frameService.loadFrame(videoTakeId, 0);
            } catch (error) {
              console.warn('Could not load first frame:', error);
            }

            // Call completion handler
            onUploadComplete({
              takeId: videoTakeId,
              frameCount: status.frame_count,
              firstFrame
            });

            setIsUploading(false);
            setUploadProgress(0);
            setCurrentTakeId(null);
          }
        } catch (error) {
          console.error('Error polling upload status:', error);
        }
      }, 2000);

      // Set a timeout to stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (isUploading && !uploadCompleteRef.current) {
          setIsUploading(false);
          setUploadProgress(0);
          setCurrentTakeId(null);
          console.error('Video upload timed out');
        }
      }, 5 * 60 * 1000);

      return { success: true };
    } catch (error) {
      setIsUploading(false);
      setUploadProgress(0);
      setCurrentTakeId(null);
      throw error;
    }
  }, [angleId, takeName, onUploadComplete, frameService]);

  const cancelUpload = useCallback(() => {
    // Reset states
    setIsUploading(false);
    setUploadProgress(0);
    setCurrentTakeId(null);
    uploadCompleteRef.current = true; // Prevent any pending callbacks
  }, []);

  return {
    uploadVideo,
    cancelUpload,
    isUploading,
    uploadProgress
  };
}