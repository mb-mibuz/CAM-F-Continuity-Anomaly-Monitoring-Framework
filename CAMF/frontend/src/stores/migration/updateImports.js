#!/usr/bin/env node

/**
 * Script to update store imports from old structure to new consolidated stores
 * 
 * Old structure:
 * - useUIStore → useAppStore
 * - useSessionStore → useAppStore
 * - useNavigationStore → useAppStore
 * - useProjectStore → useDataStore
 * - useCaptureStore → useDataStore
 * - useFrameStore → useDataStore (if any)
 * 
 * useProcessingStore remains unchanged
 */

const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Mapping of old store imports to new ones
const STORE_MAPPINGS = {
  'useUIStore': 'useAppStore',
  'useSessionStore': 'useAppStore',
  'useNavigationStore': 'useAppStore',
  'useProjectStore': 'useDataStore',
  'useCaptureStore': 'useDataStore',
  'useFrameStore': 'useDataStore'
};

// Map of old selector patterns to new ones
const SELECTOR_MAPPINGS = {
  // UI Store selectors
  'openModal': 'state => state.openModal',
  'closeModal': 'state => state.closeModal',
  'addNotification': 'state => state.addNotification',
  'removeNotification': 'state => state.removeNotification',
  'clearNotifications': 'state => state.clearNotifications',
  'setGlobalLoading': 'state => state.setGlobalLoading',
  'setGlobalError': 'state => state.setGlobalError',
  
  // Session Store selectors  
  'login': 'state => state.login',
  'logout': 'state => state.logout',
  'updatePreferences': 'state => state.updatePreferences',
  'setConnectionStatus': 'state => state.setConnectionStatus',
  
  // Navigation Store selectors
  'navigate': 'state => state.navigate',
  'goBack': 'state => state.goBack',
  'goForward': 'state => state.goForward',
  'canGoBack': 'state => state.canGoBack',
  'canGoForward': 'state => state.canGoForward',
  
  // Project Store selectors
  'setCurrentContext': 'state => state.setCurrentContext',
  'setProjects': 'state => state.setProjects',
  'getCurrentProjectScenes': 'state => state.getCurrentProjectScenes',
  'getCurrentSceneAngles': 'state => state.getCurrentSceneAngles',
  'getCurrentAngleTakes': 'state => state.getCurrentAngleTakes',
  
  // Capture Store selectors
  'setSource': 'state => state.setSource',
  'clearSource': 'state => state.clearSource',
  'startCapture': 'state => state.startCapture',
  'stopCapture': 'state => state.stopCapture',
  'updatePreviewFrame': 'state => state.updatePreviewFrame',
  'navigateFrame': 'state => state.navigateFrame'
};

function updateFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  let modified = false;
  const changes = [];

  // Track which new stores need to be imported
  const newStoresNeeded = new Set();
  const oldStoresFound = new Set();

  // Find all store imports
  const importRegex = /import\s*{\s*([^}]+)\s*}\s*from\s*['"]([^'"]*stores[^'"]*)['"]/g;
  let match;

  while ((match = importRegex.exec(content)) !== null) {
    const imports = match[1].split(',').map(imp => imp.trim());
    const importPath = match[2];
    
    // Check if this is a store import
    if (importPath.includes('stores')) {
      imports.forEach(imp => {
        if (STORE_MAPPINGS[imp]) {
          oldStoresFound.add(imp);
          newStoresNeeded.add(STORE_MAPPINGS[imp]);
        } else if (imp === 'useProcessingStore') {
          newStoresNeeded.add('useProcessingStore');
        }
      });
    }
  }

  // Update imports
  if (oldStoresFound.size > 0) {
    // Replace old imports with new ones
    content = content.replace(importRegex, (match, imports, importPath) => {
      if (!importPath.includes('stores')) return match;
      
      const importList = imports.split(',').map(imp => imp.trim());
      const updatedImports = [];
      
      importList.forEach(imp => {
        if (STORE_MAPPINGS[imp]) {
          const newStore = STORE_MAPPINGS[imp];
          if (!updatedImports.includes(newStore)) {
            updatedImports.push(newStore);
          }
        } else if (imp === 'useProcessingStore' || !imp.startsWith('use')) {
          // Keep useProcessingStore and non-store imports
          updatedImports.push(imp);
        }
      });
      
      if (updatedImports.length > 0) {
        changes.push(`Updated imports: ${importList.join(', ')} → ${updatedImports.join(', ')}`);
        return `import { ${updatedImports.join(', ')} } from '${importPath}'`;
      }
      
      return match;
    });
    
    modified = true;
  }

  // Update store usage in the code
  oldStoresFound.forEach(oldStore => {
    const newStore = STORE_MAPPINGS[oldStore];
    
    // Simple store calls: useUIStore() → useAppStore()
    const simpleRegex = new RegExp(`\\b${oldStore}\\(\\)`, 'g');
    if (simpleRegex.test(content)) {
      content = content.replace(simpleRegex, `${newStore}()`);
      changes.push(`Updated store calls: ${oldStore}() → ${newStore}()`);
      modified = true;
    }
    
    // Store calls with selectors: useUIStore(state => state.something)
    const selectorRegex = new RegExp(`\\b${oldStore}\\(([^)]+)\\)`, 'g');
    content = content.replace(selectorRegex, (match, selector) => {
      changes.push(`Updated store selector: ${oldStore}(${selector}) → ${newStore}(${selector})`);
      return `${newStore}(${selector})`;
    });
  });

  // Update specific patterns that might need adjustment
  // For example, if using destructured imports
  const destructurePatterns = [
    // const { something } = useUIStore() → const { something } = useAppStore()
    /const\s*{\s*([^}]+)\s*}\s*=\s*(useUIStore|useSessionStore|useNavigationStore)\(\)/g,
    /const\s*{\s*([^}]+)\s*}\s*=\s*(useProjectStore|useCaptureStore)\(\)/g
  ];

  destructurePatterns.forEach(pattern => {
    content = content.replace(pattern, (match, props, oldStore) => {
      if (STORE_MAPPINGS[oldStore]) {
        const newStore = STORE_MAPPINGS[oldStore];
        changes.push(`Updated destructure: ${oldStore} → ${newStore}`);
        return `const { ${props} } = ${newStore}()`;
      }
      return match;
    });
  });

  if (modified && changes.length > 0) {
    fs.writeFileSync(filePath, content);
    console.log(`✅ Updated ${path.relative(process.cwd(), filePath)}`);
    changes.forEach(change => console.log(`   - ${change}`));
    return true;
  }

  return false;
}

function findAndUpdateFiles() {
  const srcPath = path.join(__dirname, '../..');
  const patterns = [
    `${srcPath}/components/**/*.{js,jsx}`,
    `${srcPath}/pages/**/*.{js,jsx}`,
    `${srcPath}/hooks/**/*.{js,jsx}`,
    `${srcPath}/queries/**/*.{js,jsx}`,
    `${srcPath}/services/**/*.{js,jsx}`
  ];

  let totalUpdated = 0;
  let totalFiles = 0;

  patterns.forEach(pattern => {
    const files = glob.sync(pattern);
    files.forEach(file => {
      totalFiles++;
      if (updateFile(file)) {
        totalUpdated++;
      }
    });
  });

  console.log(`\n📊 Migration Summary:`);
  console.log(`   Total files scanned: ${totalFiles}`);
  console.log(`   Files updated: ${totalUpdated}`);
  console.log(`\n✨ Store migration complete!`);
  console.log(`\n⚠️  Next steps:`);
  console.log(`   1. Review the changes to ensure correctness`);
  console.log(`   2. Update any custom selectors or complex store usage`);
  console.log(`   3. Test all components thoroughly`);
  console.log(`   4. Remove old store files when ready`);
}

// Run the migration
console.log('🚀 Starting store import migration...\n');
findAndUpdateFiles();