import React, { useEffect, useCallback, Suspense } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { appWindow } from '@tauri-apps/api/window';
import { queryClient } from './queries/queryClient';
import TitleBar from './components/TitleBar';
import ResizeBorders from './components/ResizeBorders';
import HomePage from './pages/HomePage';
import ScenesPage from './pages/ScenesPage';
import TakesPage from './pages/TakesPage';
import TakeMonitoringPage from './pages/TakeMonitoringPage';
import GlobalNotifications from './components/common/GlobalNotifications';
import GlobalLoading from './components/common/GlobalLoading';
import NavigationGuard from './components/common/NavigationGuard';
import ErrorBoundary from './components/common/ErrorBoundary';
import ProcessGuard from './components/common/ProcessGuard';
import StateProvider from './components/providers/StateProvider';
import StoreDebugger from './components/dev/StoreDebugger';
import PerformanceMonitor from './components/dev/PerformanceMonitor';
import ModalManager from './components/common/ModalManager';
import { useDataStore, useAppStore } from './stores';
import './index.css';

function AppContent() {
  const { 
    getCurrentLocation, 
    navigate, 
    goBack, 
    goForward, 
    canGoBack, 
    canGoForward,
    refresh,
    isRefreshing,
    registerRefreshFunction
  } = useAppStore();
  
  const { canNavigate } = useDataStore();
  const { globalLoading, globalError } = useAppStore();
  
  const currentLocation = useAppStore(state => state.getCurrentLocation());
  const { page: currentPage, params: pageParams } = currentLocation;

  // Initialize navigation history on first mount
  useEffect(() => {
    const appState = useAppStore.getState();
    if (appState.history.length === 0) {
      // Initialize with home page
      appState.navigate('/', { replace: true });
    }
  }, []);

  useEffect(() => {
    console.log('App component mounted');
    console.log('Current page:', currentPage);
    console.log('Current params:', pageParams);
    console.log('Tauri window available:', !!appWindow);
  }, [currentPage, pageParams]);

  // Register navigation guard for capture/processing
  useEffect(() => {
    const guardId = 'app-navigation-guard';
    useAppStore.getState().registerGuard(guardId, async (to, navState) => {
      if (!canNavigate()) {
        const confirmed = await useAppStore.getState().confirm({
          title: 'Process in Progress',
          message: 'A capture or processing operation is in progress. Do you want to stop it and navigate away?',
          confirmText: 'Stop & Navigate',
          cancelText: 'Stay'
        });
        
        if (confirmed) {
          // Stop any active processes
          const dataStore = useDataStore.getState();
          if (dataStore.isCapturing) {
            await dataStore.stopCapture();
          }
          return true;
        }
        return false;
      }
      return true;
    });
    
    return () => useAppStore.getState().unregisterGuard(guardId);
  }, [canNavigate]);

  // Create a navigate wrapper that converts page/params to path
  const navigateWrapper = useCallback((page, params = {}) => {
    let path = '/';
    
    if (page === 'home') {
      path = '/';
    } else if (page === 'scenes' && params.projectId) {
      path = `/scenes/${params.projectId}`;
    } else if (page === 'takes' && params.projectId && params.sceneId) {
      path = `/takes/${params.projectId}/${params.sceneId}`;
    } else if (page === 'monitoring' && params.projectId && params.sceneId && params.angleId) {
      path = `/monitoring/${params.projectId}/${params.sceneId}/${params.angleId}`;
      if (params.takeId) {
        path += `/${params.takeId}`;
      }
    }
    
    navigate(path, { state: params });
  }, [navigate]);

  const renderPage = React.useMemo(() => {
    console.log('Rendering page:', currentPage, 'with params:', pageParams);
    
    const pageProps = {
      ...pageParams,
      onNavigate: navigateWrapper,
      onSetRefresh: (refreshFn) => registerRefreshFunction(currentPage, refreshFn)
    };
    
    switch (currentPage) {
      case 'home':
        return <HomePage {...pageProps} />;
      case 'scenes':
        return <ScenesPage {...pageProps} />;
      case 'takes':
        return <TakesPage {...pageProps} />;
      case 'monitoring':
        return <TakeMonitoringPage {...pageProps} />;
      default:
        return <HomePage {...pageProps} />;
    }
  }, [currentPage, pageParams, navigateWrapper, registerRefreshFunction]);

  return (
    <div className="h-screen w-screen flex flex-col bg-white">
      <ResizeBorders />
      
      <TitleBar 
        onGoBack={goBack}
        onGoForward={goForward}
        onGoHome={() => navigate('home')}
        canGoBack={canGoBack()}
        canGoForward={canGoForward()}
        onRefresh={refresh}
        isRefreshing={isRefreshing}
        projectName={pageParams.projectName}
        currentPage={currentPage}
      />
      
      <div className="flex-1 overflow-hidden">
        <ErrorBoundary>
          <ProcessGuard processName="CAMF" allowForceStop={true}>
            <Suspense fallback={<GlobalLoading show={true} />}>
              {renderPage}
            </Suspense>
          </ProcessGuard>
        </ErrorBoundary>
      </div>
      
      {/* Global UI components */}
      <GlobalNotifications />
      <GlobalLoading show={globalLoading} />
      <NavigationGuard />
      <StoreDebugger />
      <PerformanceMonitor />
      
      {globalError && (
        <div className="fixed bottom-4 right-4 bg-red-500 text-white p-4 rounded shadow-lg">
          {globalError}
        </div>
      )}
      
      {/* Modal Manager */}
      <ModalManager />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <StateProvider>
        <AppContent />
      </StateProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
