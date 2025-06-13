import React, { useState } from 'react';
import { 
  useAppStore,
  useDataStore,
  useProcessingStore
} from '../../stores';

export default function StoreDebugger() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('app');
  
  // Only render in development
  if (process.env.NODE_ENV !== 'development') {
    return null;
  }
  
  const stores = {
    app: useAppStore(),
    data: useDataStore(),
    processing: useProcessingStore()
  };
  
  const renderStoreState = (storeName) => {
    const state = stores[storeName];
    
    // Filter out functions
    const stateData = Object.entries(state).reduce((acc, [key, value]) => {
      if (typeof value !== 'function') {
        // Sanitize large values
        if (key.includes('frame') && typeof value === 'string' && value.length > 100) {
          acc[key] = '<FRAME_DATA>';
        } else if (value instanceof Set) {
          acc[key] = `Set(${value.size})`;
        } else if (value instanceof Map) {
          acc[key] = `Map(${value.size})`;
        } else {
          acc[key] = value;
        }
      }
      return acc;
    }, {});
    
    return (
      <pre className="text-10 overflow-auto bg-gray-100 p-2 rounded">
        {JSON.stringify(stateData, null, 2)}
      </pre>
    );
  };
  
  const getStoreActions = (storeName) => {
    const state = stores[storeName];
    return Object.entries(state)
      .filter(([key, value]) => typeof value === 'function')
      .map(([key]) => key);
  };
  
  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-4 left-4 z-50 bg-gray-800 text-white px-3 py-2 rounded-lg shadow-lg text-12 hover:bg-gray-700"
        title="Toggle Store Debugger"
      >
        🔧 Debug
      </button>
      
      {/* Debugger panel */}
      {isOpen && (
        <div className="fixed bottom-16 left-4 w-96 h-[500px] bg-white border border-gray-300 rounded-lg shadow-xl z-50 flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 border-b">
            <h3 className="text-14 font-medium">Store Debugger</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
          
          {/* Tabs */}
          <div className="flex border-b">
            {Object.keys(stores).map(storeName => (
              <button
                key={storeName}
                onClick={() => setActiveTab(storeName)}
                className={`px-3 py-2 text-12 capitalize ${
                  activeTab === storeName
                    ? 'bg-gray-100 border-b-2 border-primary'
                    : 'hover:bg-gray-50'
                }`}
              >
                {storeName}
              </button>
            ))}
          </div>
          
          {/* Content */}
          <div className="flex-1 overflow-hidden flex flex-col p-4">
            <div className="mb-2">
              <h4 className="text-12 font-medium mb-1">State</h4>
              <div className="max-h-64 overflow-auto">
                {renderStoreState(activeTab)}
              </div>
            </div>
            
            <div>
              <h4 className="text-12 font-medium mb-1">Actions</h4>
              <div className="flex flex-wrap gap-1">
                {getStoreActions(activeTab).map(action => (
                  <span
                    key={action}
                    className="text-10 bg-gray-200 px-2 py-1 rounded"
                  >
                    {action}
                  </span>
                ))}
              </div>
            </div>
            
            {/* Quick actions */}
            <div className="mt-4 pt-4 border-t">
              <h4 className="text-12 font-medium mb-2">Quick Actions</h4>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    console.log('All stores state:', {
                      app: useAppStore.getState(),
                      data: useDataStore.getState(),
                      processing: useProcessingStore.getState()
                    });
                  }}
                  className="text-10 bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600"
                >
                  Log All States
                </button>
                
                <button
                  onClick={() => {
                    if (window.confirm('Reset all stores to initial state?')) {
                      require('../../stores').resetAllStores();
                    }
                  }}
                  className="text-10 bg-red-500 text-white px-2 py-1 rounded hover:bg-red-600"
                >
                  Reset All
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}