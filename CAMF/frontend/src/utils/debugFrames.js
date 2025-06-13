// Debug utility for frame capture issues
import { buildApiUrl } from '../config';

export async function debugFrames(takeId) {
  if (!takeId) {
    console.error('[debugFrames] No takeId provided');
    return;
  }

  try {
    // Get frame debug info
    const debugResponse = await fetch(buildApiUrl(`api/frames/take/${takeId}/debug`));
    const debugData = await debugResponse.json();
    
    console.log('[Frame Debug Info]', debugData);
    
    // Get frame count
    const countResponse = await fetch(buildApiUrl(`api/frames/take/${takeId}/count`));
    const countData = await countResponse.json();
    
    console.log('[Frame Count]', countData);
    
    // Try to get first few frames
    console.log('[Testing frame retrieval]');
    for (let i = 0; i < Math.min(5, countData.count); i++) {
      try {
        const frameUrl = buildApiUrl(`api/frames/take/${takeId}/frame/${i}`);
        const frameResponse = await fetch(frameUrl);
        console.log(`Frame ${i}: ${frameResponse.status} ${frameResponse.statusText}`);
        
        if (!frameResponse.ok) {
          const errorText = await frameResponse.text();
          console.error(`Frame ${i} error:`, errorText);
        }
      } catch (error) {
        console.error(`Error fetching frame ${i}:`, error);
      }
    }
    
    return {
      debugData,
      frameCount: countData.count
    };
  } catch (error) {
    console.error('[debugFrames] Error:', error);
    throw error;
  }
}

// Helper to check frame consistency
export async function checkFrameConsistency(takeId, expectedCount) {
  const result = await debugFrames(takeId);
  
  console.log('[Frame Consistency Check]');
  console.log('Expected frames:', expectedCount);
  console.log('Database frames:', result.debugData.database_frame_count);
  console.log('Hybrid storage frames:', result.debugData.hybrid_storage?.frame_count);
  console.log('Files on disk:', result.debugData.hybrid_storage?.file_count);
  
  const issues = [];
  
  if (result.debugData.database_frame_count !== expectedCount) {
    issues.push(`Database has ${result.debugData.database_frame_count} frames, expected ${expectedCount}`);
  }
  
  if (result.debugData.hybrid_storage) {
    const hs = result.debugData.hybrid_storage;
    if (hs.frame_count !== expectedCount) {
      issues.push(`Hybrid storage has ${hs.frame_count} frames, expected ${expectedCount}`);
    }
    
    if (hs.file_count !== undefined && hs.file_count !== expectedCount) {
      issues.push(`Disk has ${hs.file_count} files, expected ${expectedCount}`);
    }
    
    // Check for gaps in frame IDs
    const frameIds = hs.frames_written;
    for (let i = 0; i < expectedCount; i++) {
      if (!frameIds.includes(i)) {
        issues.push(`Missing frame ID: ${i}`);
      }
    }
    
    // Check for extra frames
    const maxId = Math.max(...frameIds);
    if (maxId >= expectedCount) {
      issues.push(`Frame IDs go up to ${maxId}, but only ${expectedCount} frames expected`);
    }
  }
  
  if (issues.length > 0) {
    console.error('[Frame Consistency Issues]', issues);
  } else {
    console.log('[Frame Consistency] ✓ All checks passed');
  }
  
  return {
    consistent: issues.length === 0,
    issues,
    details: result
  };
}