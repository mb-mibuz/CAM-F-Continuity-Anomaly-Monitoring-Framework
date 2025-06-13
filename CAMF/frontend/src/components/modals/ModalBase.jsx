// src/components/modals/ModalBase.jsx
import React from 'react';

export default function ModalBase({ 
  children, 
  onClose, 
  preventClose = false,
  size = 'default',
  className = '',
  isOpen = true
}) {
  if (!isOpen) return null;

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget && !preventClose) {
      onClose();
    }
  };

  const getSizeClasses = () => {
    switch (size) {
      case 'small':
        return 'w-[400px]';
      case 'medium':
        return 'w-[600px]';
      case 'large':
        return 'w-[900px]';
      case 'xl':
        return 'w-[1200px]';
      case 'fullscreen':
        return 'w-full h-full m-0 rounded-none';
      default:
        return 'w-[500px]';
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className={`bg-white shadow-xl relative ${size !== 'fullscreen' ? 'rounded-lg' : ''} ${getSizeClasses()} ${className}`}>
        {/* Close button - only show for non-fullscreen modals */}
        {size !== 'fullscreen' && (
          <button 
            onClick={() => !preventClose && onClose()}
            className={`absolute top-4 right-4 w-6 h-6 flex items-center justify-center ${
              preventClose ? 'opacity-50 cursor-not-allowed' : 'btn-hover'
            }`}
            disabled={preventClose}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4L12 12M4 12L12 4" stroke="black" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        )}
        
        {children}
      </div>
    </div>
  );
}