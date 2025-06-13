import React from 'react';
import { useAppStore } from '../../stores';

import NewProjectModal from '../modals/NewProjectModal';
import NewSceneModal from '../modals/NewSceneModal';
import NewAngleModal from '../modals/NewAngleModal';
import NewTakeModal from '../modals/NewTakeModal';
import SceneConfigModal from '../modals/SceneConfigModal';
import DetectorConfigModal from '../modals/DetectorConfigModal';
import ManagePluginsModal from '../modals/ManagePluginsModal';
import SourceSelectionModal from '../modals/SourceSelectionModal';
import RenameModal from '../modals/RenameModal';
import ConfirmModal from '../modals/ConfirmModal';
import FrameLinkModal from '../modals/FrameLinkModal';
import VideoUploadModal from '../modals/VideoUploadModal';
import SourceDisconnectedModal from '../modals/SourceDisconnectedModal';
import ProcessGuardModal from '../modals/ProcessGuardModal';
import { useVideoUpload } from '../../hooks/useVideoUpload';

export default function ModalManager() {
  const modals = useAppStore(state => state.modals);
  const closeModal = useAppStore(state => state.closeModal);
  const { uploadVideo, uploading, progress } = useVideoUpload();
  
  const getModalProps = (modalName) => ({
    onClose: () => closeModal(modalName),
    ...(modals[modalName]?.data || {})
  });
  
  return (
    <>
      {/* Project Management Modals */}
      {modals.newProject.isOpen && (
        <NewProjectModal {...getModalProps('newProject')} />
      )}
      
      {modals.newScene.isOpen && (
        <NewSceneModal {...getModalProps('newScene')} />
      )}
      
      {modals.newAngle.isOpen && (
        <NewAngleModal {...getModalProps('newAngle')} />
      )}
      
      {modals.newTake.isOpen && (
        <NewTakeModal {...getModalProps('newTake')} />
      )}
      
      {/* Configuration Modals */}
      {modals.sceneConfig.isOpen && (
        <SceneConfigModal {...getModalProps('sceneConfig')} />
      )}
      
      {modals.detectorConfig.isOpen && (
        <DetectorConfigModal {...getModalProps('detectorConfig')} />
      )}
      
      {modals.managePlugins.isOpen && (
        <ManagePluginsModal {...getModalProps('managePlugins')} />
      )}
      
      {/* Capture Modals */}
      {modals.sourceSelection.isOpen && (
        <SourceSelectionModal {...getModalProps('sourceSelection')} />
      )}
      
      {modals.sourceDisconnected.isOpen && (
        <SourceDisconnectedModal {...getModalProps('sourceDisconnected')} />
      )}
      
      {/* File Upload Modal */}
      {modals.videoUpload.isOpen && (
        <VideoUploadModal 
          {...getModalProps('videoUpload')}
          onUpload={async (file) => {
            const { takeId, onSuccess } = modals.videoUpload?.data || {};
            if (takeId) {
              try {
                await uploadVideo(takeId, file);
                closeModal('videoUpload');
                if (onSuccess) {
                  onSuccess();
                }
              } catch (error) {
                console.error('Video upload failed:', error);
              }
            }
          }}
          uploading={uploading}
          progress={progress}
        />
      )}
      
      {/* Utility Modals */}
      {modals.rename.isOpen && (
        <RenameModal {...getModalProps('rename')} />
      )}
      
      {modals.confirm.isOpen && (
        <ConfirmModal {...getModalProps('confirm')} />
      )}
      
      {modals.frameLink.isOpen && (
        <FrameLinkModal {...getModalProps('frameLink')} />
      )}
      
      {/* Process Guard Modal */}
      {modals.processGuard.isOpen && (
        <ProcessGuardModal {...getModalProps('processGuard')} />
      )}
    </>
  );
}