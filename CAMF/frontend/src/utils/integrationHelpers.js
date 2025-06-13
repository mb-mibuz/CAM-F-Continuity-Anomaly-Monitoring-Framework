/**
 * Integration Test Helpers
 * 
 * Utilities to ensure all components work together correctly
 */

import { api } from './api';
import { useAppStore, useDataStore, useProcessingStore } from '../stores';
import sseEventBridge from '../services/SSEEventBridge';

/**
 * Test CRUD flow for a complete project hierarchy
 */
export async function testProjectHierarchyFlow() {
  const results = {
    project: null,
    scene: null,
    angle: null,
    take: null,
    errors: []
  };
  
  try {
    // Create project
    console.log('Creating test project...');
    results.project = await api.createProject('Integration Test Project');
    
    // Create scene
    console.log('Creating test scene...');
    results.scene = await api.createScene(results.project.id, {
      name: 'Test Scene 1',
      description: 'Integration test scene'
    });
    
    // Create angle
    console.log('Creating test angle...');
    results.angle = await api.createAngle(results.scene.id, {
      name: 'Angle 1'
    });
    
    // Create take
    console.log('Creating test take...');
    results.take = await api.createTake(results.angle.id, {
      name: 'Take 1',
      is_reference: true
    });
    
    // Update data store
    const dataStore = useDataStore.getState();
    dataStore.setCurrentContext({
      project: results.project,
      scene: results.scene,
      angle: results.angle,
      take: results.take
    });
    
    console.log('Project hierarchy created successfully:', results);
    
  } catch (error) {
    console.error('Project hierarchy creation failed:', error);
    results.errors.push(error);
  }
  
  return results;
}

/**
 * Test capture to processing flow
 */
export async function testCaptureToProcessingFlow(takeId) {
  const results = {
    captureStarted: false,
    framesCaptured: 0,
    processingStarted: false,
    processingCompleted: false,
    errors: []
  };
  
  const dataStore = useDataStore.getState();
  const processingStore = useProcessingStore.getState();
  
  try {
    // Simulate capture
    console.log('Starting simulated capture...');
    
    // Set a test source
    dataStore.setSource({
      type: 'test',
      name: 'Test Source',
      id: 'test-1'
    });
    
    // Start capture
    await dataStore.startCapture(takeId, {
      frameRate: 24,
      frame_count_limit: 10 // Capture 10 frames for test
    });
    results.captureStarted = true;
    
    // Simulate frame capture
    for (let i = 0; i < 10; i++) {
      dataStore.updateCaptureProgress({
        capturedFrames: i + 1,
        processedFrames: i
      });
      
      // Simulate SSE frame event
      sseEventBridge.handleFrameCaptured({
        takeId,
        frameIndex: i,
        preview: `data:image/png;base64,test-frame-${i}`
      });
      
      await new Promise(resolve => setTimeout(resolve, 100)); // 100ms between frames
    }
    
    results.framesCaptured = 10;
    
    // Stop capture
    await dataStore.stopCapture();
    
    // Start processing
    console.log('Starting processing...');
    processingStore.startProcessing(takeId, {
      totalFrames: 10,
      detectors: ['test-detector']
    });
    results.processingStarted = true;
    
    // Simulate processing progress
    for (let i = 0; i < 10; i++) {
      processingStore.updateProcessingProgress({
        currentFrame: i + 1,
        processedFrames: i + 1
      });
      
      await new Promise(resolve => setTimeout(resolve, 50)); // 50ms per frame
    }
    
    // Complete processing
    processingStore.completeProcessing(takeId);
    results.processingCompleted = true;
    
    console.log('Capture to processing flow completed:', results);
    
  } catch (error) {
    console.error('Capture to processing flow failed:', error);
    results.errors.push(error);
  }
  
  return results;
}

/**
 * Test SSE real-time updates
 */
export async function testSSEUpdates() {
  const results = {
    connected: false,
    eventsReceived: [],
    errors: []
  };
  
  try {
    // Check SSE connection
    const sseService = sseEventBridge.sseService;
    results.connected = sseService.isConnected;
    
    if (!results.connected) {
      console.log('Attempting to connect SSE...');
      await sseService.connect();
      results.connected = sseService.isConnected;
    }
    
    // Subscribe to test events
    const unsubscribe = sseService.subscribe('test_events', (message) => {
      results.eventsReceived.push(message);
      console.log('Received test event:', message);
    });
    
    // Wait for some events
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Cleanup
    unsubscribe();
    
    console.log('SSE test completed:', results);
    
  } catch (error) {
    console.error('SSE test failed:', error);
    results.errors.push(error);
  }
  
  return results;
}

/**
 * Test store synchronization
 */
export function testStoreSynchronization() {
  const results = {
    storesInSync: true,
    discrepancies: [],
    errors: []
  };
  
  try {
    const dataStore = useDataStore.getState();
    const processingStore = useProcessingStore.getState();
    
    // Check if current take is consistent across stores
    const currentTake = dataStore.currentTake;
    
    if (currentTake) {
      // Check frame count consistency
      const projectFrameCount = currentTake.frame_count || 0;
      const captureFrameCount = dataStore.frameCount;
      
      if (projectFrameCount !== captureFrameCount) {
        results.storesInSync = false;
        results.discrepancies.push({
          type: 'frame_count',
          projectStore: projectFrameCount,
          dataStore: captureFrameCount
        });
      }
      
      // Check processing status consistency
      const isProcessing = processingStore.isProcessing;
      const processingTakeId = processingStore.processingSession?.takeId;
      
      if (isProcessing && processingTakeId !== currentTake.id) {
        results.storesInSync = false;
        results.discrepancies.push({
          type: 'processing_take_mismatch',
          currentTakeId: currentTake.id,
          processingTakeId
        });
      }
    }
    
    // Check navigation ability consistency
    const captureCanNavigate = dataStore.canNavigate();
    const processingCanNavigate = processingStore.canNavigate();
    
    if (captureCanNavigate !== processingCanNavigate) {
      results.storesInSync = false;
      results.discrepancies.push({
        type: 'navigation_ability',
        dataStore: captureCanNavigate,
        processingStore: processingCanNavigate
      });
    }
    
    console.log('Store synchronization test:', results);
    
  } catch (error) {
    console.error('Store synchronization test failed:', error);
    results.errors.push(error);
  }
  
  return results;
}

/**
 * Run all integration tests
 */
export async function runAllIntegrationTests() {
  console.log('=== Starting Integration Tests ===');
  
  const allResults = {
    projectHierarchy: null,
    captureToProcessing: null,
    sse: null,
    storeSynchronization: null,
    overallSuccess: true
  };
  
  try {
    // Test 1: Project hierarchy
    console.log('\n1. Testing project hierarchy CRUD...');
    allResults.projectHierarchy = await testProjectHierarchyFlow();
    
    if (allResults.projectHierarchy.errors.length > 0) {
      allResults.overallSuccess = false;
    }
    
    // Test 2: Capture to processing (only if we have a take)
    if (allResults.projectHierarchy.take) {
      console.log('\n2. Testing capture to processing flow...');
      allResults.captureToProcessing = await testCaptureToProcessingFlow(
        allResults.projectHierarchy.take.id
      );
      
      if (allResults.captureToProcessing.errors.length > 0) {
        allResults.overallSuccess = false;
      }
    }
    
    // Test 3: SSE
    console.log('\n3. Testing SSE real-time updates...');
    allResults.sse = await testSSEUpdates();
    
    if (allResults.sse.errors.length > 0) {
      allResults.overallSuccess = false;
    }
    
    // Test 4: Store synchronization
    console.log('\n4. Testing store synchronization...');
    allResults.storeSynchronization = testStoreSynchronization();
    
    if (!allResults.storeSynchronization.storesInSync) {
      allResults.overallSuccess = false;
    }
    
    // Cleanup test data
    if (allResults.projectHierarchy.project) {
      console.log('\nCleaning up test data...');
      try {
        await api.deleteProject(allResults.projectHierarchy.project.id);
      } catch (error) {
        console.error('Failed to cleanup test project:', error);
      }
    }
    
  } catch (error) {
    console.error('Integration tests failed:', error);
    allResults.overallSuccess = false;
  }
  
  console.log('\n=== Integration Tests Complete ===');
  console.log('Overall success:', allResults.overallSuccess);
  console.log('Results:', allResults);
  
  return allResults;
}

// Export for use in browser console
if (typeof window !== 'undefined') {
  window.CAMFIntegrationTests = {
    testProjectHierarchyFlow,
    testCaptureToProcessingFlow,
    testSSEUpdates,
    testStoreSynchronization,
    runAllIntegrationTests
  };
  
  console.log('CAMF Integration Tests loaded. Access via window.CAMFIntegrationTests');
}