import React, { useRef, useCallback, useState } from 'react';
import { FileText } from 'lucide-react';
import { useAppStore } from '../../../stores';
import { api } from '../../../utils/api';
import { buildApiUrl } from '../../../config';
import NotesSection from '../../../components/monitoring/NotesSection';
import { save } from '@tauri-apps/api/dialog';
import { writeBinaryFile } from '@tauri-apps/api/fs';
import ExportProgressModal from '../../../components/modals/ExportProgressModal';

export default function NotesEditor({
  takeId,
  takeName,
  sceneName,
  initialNotes,
  frameCount,
  currentFrameIndex,
  isDisabled
}) {
  const notesRef = useRef(null);
  const { addNotification, openModal, closeModal } = useAppStore();
  const [exportProgress, setExportProgress] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  
  // Handle notes change with auto-save
  const handleNotesChange = useCallback(async (markdown) => {
    try {
      await api.updateTake(takeId, { notes: markdown });
    } catch (error) {
      console.error('Failed to save notes:', error);
      // Don't show error notification for auto-save failures
    }
  }, [takeId]);

  // Handle export
  const handleExport = useCallback(async () => {
    if (frameCount === 0 || isDisabled || isExporting) return;
    
    setIsExporting(true);
    setExportProgress({
      status: 'preparing',
      currentStep: 'Initializing export...',
      stepsCompleted: 0,
      totalSteps: 4
    });
    
    try {
      // Step 1: Gather data
      setExportProgress({
        status: 'gathering_data',
        currentStep: 'Gathering take data and notes...',
        stepsCompleted: 1,
        totalSteps: 4
      });
      
      // First, fetch the PDF from the backend with timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout
      
      // Step 2: Process frames
      setExportProgress({
        status: 'processing_frames',
        currentStep: 'Processing frames and error detection results...',
        stepsCompleted: 2,
        totalSteps: 4
      });
      
      const response = await fetch(buildApiUrl(`api/export/take/${takeId}/pdf`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }
      
      // Step 3: Generate PDF
      setExportProgress({
        status: 'generating_pdf',
        currentStep: 'Generating PDF document...',
        stepsCompleted: 3,
        totalSteps: 4
      });
      
      // Get the PDF as blob
      console.log('Getting PDF blob...');
      const blob = await response.blob();
      console.log('PDF blob size:', blob.size);
      
      // Convert blob to Uint8Array for Tauri
      console.log('Converting to array buffer...');
      const arrayBuffer = await blob.arrayBuffer();
      const uint8Array = new Uint8Array(arrayBuffer);
      console.log('Array buffer size:', uint8Array.length);
      
      // Open save dialog
      const filePath = await save({
        defaultPath: `${sceneName}_${takeName}_notes.pdf`,
        filters: [{
          name: 'PDF Files',
          extensions: ['pdf']
        }]
      });
      
      if (filePath) {
        // Step 4: Save file
        setExportProgress({
          status: 'finalizing',
          currentStep: 'Saving PDF file...',
          stepsCompleted: 4,
          totalSteps: 4
        });
        
        // Write the file
        await writeBinaryFile(filePath, uint8Array);
        
        // Mark as complete
        setExportProgress({
          status: 'complete',
          currentStep: '',
          stepsCompleted: 4,
          totalSteps: 4
        });
        
        addNotification({ 
          type: 'success', 
          message: 'Notes exported successfully',
          duration: 7000 
        });
        
        // Auto-close modal after a short delay
        setTimeout(() => {
          setExportProgress(null);
          setIsExporting(false);
        }, 2000);
      } else {
        // User cancelled save dialog
        setExportProgress(null);
        setIsExporting(false);
      }
    } catch (error) {
      console.error('Failed to export notes:', error);
      setExportProgress({
        status: 'error',
        message: error.message || 'Failed to export PDF',
        currentStep: '',
        stepsCompleted: 0,
        totalSteps: 0
      });
      
      addNotification({ 
        type: 'error', 
        message: `Failed to export notes: ${error.message || 'Unknown error'}` 
      });
      
      // Keep error modal open for user to read
      setTimeout(() => {
        setIsExporting(false);
      }, 3000);
    }
  }, [takeId, takeName, sceneName, frameCount, isDisabled, isExporting, addNotification]);

  // Handle clear notes
  const handleClear = useCallback(async () => {
    const confirmed = await useAppStore.getState().confirm({
      title: 'Clear Notes',
      message: 'Are you sure you want to clear all notes? This action cannot be undone.',
      confirmText: 'Clear',
      cancelText: 'Cancel'
    });
    
    if (confirmed) {
      if (notesRef.current) {
        notesRef.current.setHtml('');
        await handleNotesChange('');
        addNotification({ type: 'success', message: 'Notes cleared' });
      }
    }
  }, [handleNotesChange, addNotification]);

  // Handle link frame
  const handleLinkFrame = useCallback(() => {
    if (frameCount === 0) {
      addNotification({ type: 'warning', message: 'No frames available to link' });
      return;
    }
    
    openModal('frameLink', {
      takeId,
      maxFrame: frameCount - 1,
      currentFrame: currentFrameIndex,
      onConfirm: (frameNumber) => {
        // Insert frame link at cursor position
        if (notesRef.current) {
          const linkHtml = `<em>Frame #${frameNumber}</em>`;
          notesRef.current.insertAtCursor(linkHtml);
        }
        
        closeModal('frameLink');
      }
    });
  }, [frameCount, currentFrameIndex, takeId, openModal, closeModal, addNotification]);


  return (
    <div className="h-full flex flex-col px-6 pb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pt-4">
        <h3 className="text-16 font-medium">Notes</h3>
        <button
          onClick={handleExport}
          disabled={frameCount === 0 || isDisabled}
          className={`
            flex items-center gap-2 text-14
            ${frameCount === 0 || isDisabled
              ? 'text-gray-400 cursor-not-allowed'
              : 'text-primary hover:opacity-80'
            }
          `}
          title={frameCount === 0 ? 'No frames to export' : 'Export to PDF'}
        >
          <FileText size={16} />
          <span>Export</span>
        </button>
      </div>
      
      {/* Notes editor */}
      <div className="flex-1 min-h-0">
        <NotesSection
          ref={notesRef}
          initialNotes={initialNotes}
          onNotesChange={handleNotesChange}
          onExport={handleExport}
          onClear={handleClear}
          onLinkFrame={handleLinkFrame}
          frameCount={frameCount}
          isExportDisabled={isDisabled}
        />
      </div>
      
      {/* Help text */}
      <div className="mt-3 text-gray-400" style={{ fontSize: '10px', lineHeight: '1.3' }}>
        <p>Use the toolbar to format text and link to specific frames.</p>
        <p>Notes are automatically saved as you type.</p>
      </div>
      
      {/* Export Progress Modal */}
      <ExportProgressModal
        isOpen={exportProgress !== null}
        onClose={() => {
          setExportProgress(null);
          setIsExporting(false);
        }}
        progress={exportProgress}
      />
    </div>
  );
}