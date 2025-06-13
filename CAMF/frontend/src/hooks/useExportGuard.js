import { useState, useCallback } from 'react';
import { useAppStore } from '../stores';
import { api } from '../utils/api';
import config, { buildApiUrl } from '../config';

export function useExportGuard() {
  const [isExporting, setIsExporting] = useState(false);
  const { addNotification } = useAppStore();

  const exportWithGuard = useCallback(async (exportFn, options = {}) => {
    const {
      entityType = 'data',
      entityName = '',
      checkContent = null
    } = options;

    if (isExporting) {
      addNotification({ type: 'warning', message: 'An export is already in progress. Please wait.' });
      return false;
    }

    try {
      setIsExporting(true);

      // Check if there's content to export if validation function provided
      if (checkContent) {
        const hasContent = await checkContent();
        if (!hasContent) {
          addNotification({ type: 'warning', message: `Cannot export ${entityType}: No content to export.` });
          return false;
        }
      }

      // Show progress notification
      // Note: Loading notifications not supported in new structure
      addNotification({ type: 'info', message: `Exporting ${entityType}...` });

      // Perform export
      const result = await exportFn();

      // Update notification on success
      // Dismiss not needed without progressId
      addNotification({ type: 'success', message: `${entityType} exported successfully!` });

      return result;

    } catch (error) {
      console.error(`Error exporting ${entityType}:`, error);
      
      // Determine error message
      let errorMessage = 'Unknown error occurred';
      
      if (error.response) {
        // API error response
        if (error.response.status === 404) {
          errorMessage = `${entityType} not found`;
        } else if (error.response.status === 400) {
          errorMessage = error.response.data?.detail || 'Invalid request';
        } else if (error.response.status === 500) {
          errorMessage = 'Server error occurred';
        } else {
          errorMessage = error.response.data?.detail || error.message;
        }
      } else if (error.message) {
        errorMessage = error.message;
      }

      addNotification({ type: 'error', message: `Failed to export ${entityType}: ${errorMessage}` });
      return false;

    } finally {
      setIsExporting(false);
    }
  }, [isExporting, addNotification]);

  const exportTake = useCallback(async (takeId, takeName, filePath) => {
    return exportWithGuard(
      async () => {
        // Check if take has frames first
        const response = await fetch(buildApiUrl(`api/frames/take/${takeId}/frame/0`));
        if (!response.ok) {
          throw new Error('No frames captured yet');
        }
        
        // Get the PDF as blob
        const pdfResponse = await fetch(buildApiUrl(`api/export/take/${takeId}/pdf`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });
        
        if (!pdfResponse.ok) {
          throw new Error(`Export failed: ${pdfResponse.statusText}`);
        }
        
        const blob = await pdfResponse.blob();
        const arrayBuffer = await blob.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // Use Tauri to write the file
        const { writeBinaryFile } = await import('@tauri-apps/api/fs');
        await writeBinaryFile(filePath, uint8Array);
        
        return { success: true };
      },
      {
        entityType: 'Take',
        entityName: takeName
      }
    );
  }, [exportWithGuard]);

  const exportScene = useCallback(async (sceneId, sceneName, filePath, checkFunction) => {
    return exportWithGuard(
      async () => {
        // Get the PDF as blob
        const pdfResponse = await fetch(buildApiUrl(`api/export/scene/${sceneId}/pdf`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });
        
        if (!pdfResponse.ok) {
          throw new Error(`Export failed: ${pdfResponse.statusText}`);
        }
        
        const blob = await pdfResponse.blob();
        const arrayBuffer = await blob.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // Use Tauri to write the file
        const { writeBinaryFile } = await import('@tauri-apps/api/fs');
        await writeBinaryFile(filePath, uint8Array);
        
        return { success: true };
      },
      {
        entityType: 'Scene',
        entityName: sceneName,
        checkContent: checkFunction
      }
    );
  }, [exportWithGuard]);

  const exportProject = useCallback(async (projectId, projectName, filePath, checkFunction) => {
    return exportWithGuard(
      async () => {
        // Get the PDF as blob
        const pdfResponse = await fetch(buildApiUrl(`api/export/project/${projectId}/pdf`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });
        
        if (!pdfResponse.ok) {
          throw new Error(`Export failed: ${pdfResponse.statusText}`);
        }
        
        const blob = await pdfResponse.blob();
        const arrayBuffer = await blob.arrayBuffer();
        const uint8Array = new Uint8Array(arrayBuffer);
        
        // Use Tauri to write the file
        const { writeBinaryFile } = await import('@tauri-apps/api/fs');
        await writeBinaryFile(filePath, uint8Array);
        
        return { success: true };
      },
      {
        entityType: 'Project',
        entityName: projectName,
        checkContent: checkFunction
      }
    );
  }, [exportWithGuard]);

  return {
    isExporting,
    exportTake,
    exportScene,
    exportProject,
    exportWithGuard
  };
}