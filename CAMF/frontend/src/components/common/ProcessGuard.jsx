import React, { memo } from 'react';
import { useProcessGuard } from '../../hooks/useProcessGuard';

const ProcessGuard = memo(function ProcessGuard({ 
  children, 
  processName = 'Process',
  allowForceStop = true,
  customMessage = null 
}) {
  // Use the hook which handles all the logic
  useProcessGuard({
    processName,
    allowForceStop,
    customMessage
  });

  // Just render children - all guard logic is in the hook
  return <>{children}</>;
});

export default ProcessGuard;