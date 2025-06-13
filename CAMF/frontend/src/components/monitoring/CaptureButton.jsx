import React, { memo } from 'react';

const CaptureButton = memo(({ 
  isCapturing, 
  onStart, 
  onStop, 
  disabled = false,
  size = 'medium' 
}) => {
  const sizes = {
    small: { button: 'w-8 h-8', border: 'border-2', inner: 'w-6 h-6', innerRecording: 'w-3 h-3' },
    medium: { button: 'w-10 h-10', border: 'border-[2.5px]', inner: 'w-7 h-7', innerRecording: 'w-4 h-4' },
    large: { button: 'w-12 h-12', border: 'border-[3px]', inner: 'w-9 h-9', innerRecording: 'w-5 h-5' }
  };
  
  const sizeConfig = sizes[size] || sizes.medium;
  
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!disabled) {
      if (isCapturing) {
        onStop?.();
      } else {
        onStart?.();
      }
    }
  };
  
  return (
    <button
      onClick={handleClick}
      onMouseDown={(e) => e.preventDefault()}
      disabled={disabled}
      title=""
      className={`
        relative ${sizeConfig.button} flex items-center justify-center 
        transition-transform duration-150
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:scale-110 cursor-pointer'}
      `}
      style={{ touchAction: 'none', WebkitTapHighlightColor: 'transparent' }}
    >
      <div className={`absolute inset-0 rounded-full ${sizeConfig.border} border-red-600`} />
      <div className={`
        bg-red-600 transition-all duration-200 ease-in-out pointer-events-none
        ${isCapturing 
          ? `${sizeConfig.innerRecording} rounded-[3px] animate-pulse` 
          : `${sizeConfig.inner} rounded-full`
        }
      `} />
    </button>
  );
});

CaptureButton.displayName = 'CaptureButton';

export default CaptureButton;