import { useEffect } from 'react';

/**
 * Hook for global keyboard shortcuts
 * @param {Object} shortcuts - Object mapping key combos to handlers
 * @param {boolean} enabled - Whether shortcuts are enabled
 */
export function useKeyboardShortcuts(shortcuts, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    
    const handleKeyDown = (e) => {
      const key = e.key.toLowerCase();
      const ctrl = e.ctrlKey || e.metaKey;
      const shift = e.shiftKey;
      const alt = e.altKey;
      
      // Build key combo string
      const combo = [
        ctrl && 'ctrl',
        shift && 'shift',
        alt && 'alt',
        key
      ].filter(Boolean).join('+');
      
      // Check if we have a handler for this combo
      if (shortcuts[combo]) {
        e.preventDefault();
        shortcuts[combo](e);
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [shortcuts, enabled]);
}
