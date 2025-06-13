import React from 'react';
import { useAppStore } from '../../stores';

export default function GlobalLoading({ show }) {
  const loadingMessage = useAppStore(state => state.loadingMessage);
  
  if (!show) return null;
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 shadow-xl">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4"></div>
          <p className="text-16 font-medium">{loadingMessage || 'Loading...'}</p>
        </div>
      </div>
    </div>
  );
}