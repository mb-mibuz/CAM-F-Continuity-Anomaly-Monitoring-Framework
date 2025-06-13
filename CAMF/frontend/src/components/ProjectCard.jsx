import React, { useState } from 'react';
import RenameModal from './modals/RenameModal';
import ConfirmModal from './modals/ConfirmModal';
import { buildApiUrl } from '../config';

export default function ProjectCard({ project, onClick, onRename, onDelete, onExport, onOpenLocation }) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const handleRename = (newName) => {
    onRename(newName);
    setShowRenameModal(false);
  };

  const handleDelete = () => {
    onDelete();
    setShowDeleteModal(false);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Just now';
    
    const date = new Date(dateString);
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return 'Just now';
    }
    
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffMinutes = Math.floor(diffTime / (1000 * 60));
    const diffHours = Math.floor(diffTime / (1000 * 60 * 60));
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffMinutes < 1) return 'Just now';
    if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return '1 day ago';
    if (diffDays < 30) return `${diffDays} days ago`;
    if (diffDays < 365) {
      const months = Math.floor(diffDays / 30);
      return months === 1 ? '1 month ago' : `${months} months ago`;
    }
    const years = Math.floor(diffDays / 365);
    return years === 1 ? '1 year ago' : `${years} years ago`;
  };

  return (
    <>
      <div 
        className="w-[357px] h-[280px] border-0.25 border-black card-hover cursor-pointer overflow-hidden"
        onClick={onClick}
      >
        {/* Thumbnail - 16:9 aspect ratio */}
        <div className="w-full h-[201px] bg-card-gray relative overflow-hidden">
          {/* 357px width * 9/16 = 200.8px height, rounded to 201px */}
          <img 
            src={buildApiUrl(`api/projects/${project.id}/thumbnail`)}
            alt={`${project.name} thumbnail`}
            className="absolute inset-0 w-full h-full object-cover"
            style={{
              objectFit: 'cover',
              objectPosition: 'center'
            }}
            onError={(e) => {
              // Hide image on error to show gray background
              e.target.style.display = 'none';
            }}
          />
        </div>
        
        {/* Content */}
        <div className="h-[79px] px-4 py-3 flex items-center justify-between overflow-hidden">
          <div className="flex-1 min-w-0 pr-2 overflow-hidden max-w-[240px]">
            <h3 className="text-14 font-normal truncate block w-full" title={project.name}>{project.name}</h3>
            <p className="text-12 font-normal text-text-gray truncate w-full">{formatDate(project.last_modified || project.created_at)}</p>
          </div>
          
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Edit button */}
            <button 
              onClick={(e) => {
                e.stopPropagation();
                setShowRenameModal(true);
              }}
              className="w-6 h-6 flex items-center justify-center btn-hover"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M11.5 2.5L13.5 4.5L11.5 2.5ZM12.5 1.5L8 6L7 9L10 8L14.5 3.5C14.8 3.2 15 2.8 15 2.5C15 2.2 14.8 1.8 14.5 1.5C14.2 1.2 13.8 1 13.5 1C13.2 1 12.8 1.2 12.5 1.5V1.5Z" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M13 9V13C13 13.5 12.5 14 12 14H3C2.5 14 2 13.5 2 13V4C2 3.5 2.5 3 3 3H7" stroke="black" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            
            {/* More options button */}
            <div className="relative">
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  setShowDropdown(!showDropdown);
                }}
                className="w-6 h-6 flex items-center justify-center btn-hover"
              >
                <svg width="16" height="4" viewBox="0 0 16 4" fill="none">
                  <circle cx="2" cy="2" r="1.5" fill="black"/>
                  <circle cx="8" cy="2" r="1.5" fill="black"/>
                  <circle cx="14" cy="2" r="1.5" fill="black"/>
                </svg>
              </button>
              
              {showDropdown && (
                <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 w-40">
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      onOpenLocation();
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Open location
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      onExport();
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14"
                  >
                    Export as PDF
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDropdown(false);
                      setShowDeleteModal(true);
                    }}
                    className="block w-full text-left px-4 py-2 hover:bg-gray-100 text-14 text-red-600"
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showRenameModal && (
        <RenameModal 
          title="Rename Project"
          currentName={project.name}
          onClose={() => setShowRenameModal(false)}
          onSave={handleRename}
        />
      )}

      {showDeleteModal && (
        <ConfirmModal 
          title="Delete Project"
          message={`Are you sure you want to delete "${project.name}"? This action cannot be undone.`}
          confirmText="Delete"
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteModal(false)}
        />
      )}
    </>
  );
}