"""
Integration verification for all backend services.
"""

import json
from typing import Dict, Any
from datetime import datetime


class IntegrationVerifier:
    """Verifies all backend services are properly integrated."""
    
    @staticmethod
    def verify_all_integrations() -> Dict[str, Any]:
        """Run all integration checks."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks': {}
        }
        
        # Performance monitoring and GPU management removed - handled by separate testing framework
        
        # Check detector framework integration
        results['checks']['detector_framework'] = IntegrationVerifier._check_detector_framework()
        
        # Check multi-language support
        results['checks']['multilang_support'] = IntegrationVerifier._check_multilang_support()
        
        # Check version control
        results['checks']['version_control'] = IntegrationVerifier._check_version_control()
        
        return results
    
    
    @staticmethod
    def _check_detector_framework() -> Dict[str, Any]:
        """Check detector framework integration."""
        try:
            from CAMF.services.detector_framework import get_detector_framework_service
            
            service = get_detector_framework_service()
            
            # Check components
            has_installer = hasattr(service, 'installer') and service.installer is not None
            has_process_manager = hasattr(service, 'process_manager') and service.process_manager is not None
            has_recovery = hasattr(service, 'recovery_manager') and service.recovery_manager is not None
            
            return {
                'status': 'ok' if all([has_installer, has_process_manager, has_recovery]) else 'failed',
                'has_installer': has_installer,
                'has_process_manager': has_process_manager,
                'has_recovery': has_recovery
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    @staticmethod
    def _check_multilang_support() -> Dict[str, Any]:
        """Check multi-language support."""
        try:
            from CAMF.services.detector_framework.language_support import LanguageSupportManager
            
            manager = LanguageSupportManager()
            
            # Check runtime support
            runtime_count = len(manager.runtimes)
            
            # Check protocol handlers
            protocol_count = len(manager.protocol_handlers)
            
            return {
                'status': 'ok',
                'runtime_count': runtime_count,
                'protocol_count': protocol_count
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    @staticmethod
    def _check_version_control() -> Dict[str, Any]:
        """Check version control system."""
        try:
            from CAMF.services.detector_framework.version_control import DetectorVersionControl
            
            vc = DetectorVersionControl("detectors")
            
            # Check if version index exists
            has_index = vc.version_index_file.exists()
            
            return {
                'status': 'ok',
                'has_index': has_index,
                'index_path': str(vc.version_index_file)
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}


# Run verification
if __name__ == "__main__":
    results = IntegrationVerifier.verify_all_integrations()
    print(json.dumps(results, indent=2))