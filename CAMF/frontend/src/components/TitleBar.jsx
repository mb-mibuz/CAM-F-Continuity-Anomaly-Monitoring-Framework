// src/components/TitleBar.jsx
import React, { useState } from 'react';
import { appWindow } from '@tauri-apps/api/window';
import { RefreshCw } from 'lucide-react';
import logoSvg from '../assets/images/logo.svg';

export default function TitleBar({ 
  onGoBack, 
  onGoForward, 
  onGoHome, 
  canGoBack, 
  canGoForward,
  onRefresh,
  isRefreshing = false,
  projectName,
  currentPage
}) {
  const [isMaximized, setIsMaximized] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  const handleMinimize = () => {
    appWindow.minimize();
  };

  const handleMaximize = async () => {
    const maximized = await appWindow.isMaximized();
    if (maximized) {
      await appWindow.unmaximize();
      setIsMaximized(false);
    } else {
      await appWindow.maximize();
      setIsMaximized(true);
    }
  };

  const handleClose = () => {
    appWindow.close();
  };

  const openGitHub = () => {
    window.open('https://github.com/mb-mibuz/CAM-F-Continuity-Anomaly-Monitoring-Framework', '_blank');
  };

  return (
    <>
      <div className="h-[77px] flex flex-col no-select">
        <div className="h-2"></div>
        <div 
          className="h-[70px] relative flex items-center px-9 bg-white titlebar-drag-region"
          data-tauri-drag-region
        >
          {/* Left side - Navigation */}
          <div className="flex items-center gap-4 titlebar-no-drag">
            {/* Menu dots */}
            <button 
              onClick={() => setShowMenu(!showMenu)}
              className="relative w-9 h-5 flex items-center justify-center btn-hover"
            >
              <div className="flex gap-1">
                <div className="w-1 h-1 bg-black rounded-full"></div>
                <div className="w-1 h-1 bg-black rounded-full"></div>
                <div className="w-1 h-1 bg-black rounded-full"></div>
              </div>
            </button>

            {/* Back arrow */}
            <button 
              onClick={onGoBack}
              disabled={!canGoBack}
              className={`w-6 h-6 flex items-center justify-center btn-hover ${!canGoBack ? 'opacity-30' : ''}`}
            >
              <svg width="8" height="12" viewBox="0 0 8 12" fill="none">
                <path d="M7 1L2 6L7 11" stroke="black" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>

            {/* Forward arrow */}
            <button 
              onClick={onGoForward}
              disabled={!canGoForward}
              className={`w-6 h-6 flex items-center justify-center btn-hover ${!canGoForward ? 'opacity-30' : ''}`}
            >
              <svg width="8" height="12" viewBox="0 0 8 12" fill="none">
                <path d="M1 1L6 6L1 11" stroke="black" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>

            {/* Home icon */}
            <button 
              onClick={onGoHome}
              className="w-7 h-8 flex items-center justify-center btn-hover"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 7L10 2L17 7V17C17 17.5 16.5 18 16 18H4C3.5 18 3 17.5 3 17V7Z" stroke="black" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>

            {/* Add refresh button after home button */}
            <button 
              onClick={onRefresh}
              disabled={!onRefresh || isRefreshing}
              className={`w-7 h-8 flex items-center justify-center btn-hover ${
                (!onRefresh || isRefreshing) ? 'opacity-30' : ''
              }`}
              title="Refresh"
            >
              <RefreshCw 
                size={20} 
                strokeWidth={2}
                className={isRefreshing ? 'animate-spin' : ''}
              />
            </button>
            
            {/* Project name - show when not on home page */}
            {currentPage !== 'home' && projectName && (
              <>
                <div className="mx-3 w-px h-6 bg-gray-300"></div>
                <span className="text-14 font-medium text-gray-700">{projectName}</span>
              </>
            )}
          </div>

          {/* Center - Logo (absolutely positioned) */}
          <div className="absolute left-1/2 transform -translate-x-1/2 pointer-events-none">
            <img 
              src={logoSvg} 
              alt="CAMF Logo" 
              className="titlebar-logo"
              style={{ 
                height: '25px',
                width: 'auto',
                filter: 'invert(15%)'
              }}
            />
          </div>

          {/* Right side - Window controls */}
          <div className="flex items-center gap-4 titlebar-no-drag ml-auto">
            {/* Minimize */}
            <button 
              onClick={handleMinimize}
              className="w-5 h-5 flex items-center justify-center btn-hover"
            >
              <div className="w-5 h-0.5 bg-black"></div>
            </button>

            {/* Maximize/Restore */}
            <button 
              onClick={handleMaximize}
              className="w-5 h-5 flex items-center justify-center btn-hover"
            >
              <div className={`border-2.5 border-black ${isMaximized ? 'w-4 h-4' : 'w-5 h-5'}`}></div>
            </button>

            {/* Close */}
            <button 
              onClick={handleClose}
              className="w-8 h-8 flex items-center justify-center btn-hover"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M5 5L15 15M5 15L15 5" stroke="black" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Bottom line separator */}
        <div className="separator-line w-full"></div>
      </div>

      {/* Dropdown menu */}
      {showMenu && (
        <div className="absolute top-16 left-9 bg-white border border-gray-200 rounded shadow-lg z-50">
          <button 
            onClick={() => {
              openGitHub();
              setShowMenu(false);
            }}
            className="block w-full text-left px-4 py-2 hover:bg-gray-100"
          >
            Open GitHub
          </button>
          <button 
            onClick={() => {
              // Add more menu items here
              setShowMenu(false);
            }}
            className="block w-full text-left px-4 py-2 hover:bg-gray-100"
          >
            About
          </button>
        </div>
      )}
    </>
  );
}