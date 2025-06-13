# CAMF/launcher.py
"""
Main launcher for CAMF application.
Starts all services in a single process and opens the web UI.
"""

import sys
import time
import threading
import webbrowser
import signal
from pathlib import Path

# Add CAMF to path
camf_root = Path(__file__).parent.parent
if str(camf_root) not in sys.path:
    sys.path.insert(0, str(camf_root))

from CAMF.services.api_gateway.main import main as start_api_gateway
from CAMF.services.storage import get_storage_service
from CAMF.services.capture import get_capture_service
from CAMF.services.detector_framework import get_detector_framework_service


class CAMFApplication:
    """Main CAMF application controller."""
    
    def __init__(self):
        self.services = {}
        self.running = False
        self.api_thread = None
        
    def start(self):
        """Start all CAMF services."""
        print("Starting CAMF services...")
        
        try:
            # Initialize storage (with integrated frame provider)
            print("Initializing storage service...")
            self.services['storage'] = get_storage_service()
            
            # Start core services
            print("Starting capture service...")
            self.services['capture'] = get_capture_service()
            
            print("Starting detector framework...")
            self.services['detector_framework'] = get_detector_framework_service()
            
            # Start API gateway in thread
            print("Starting API gateway...")
            self.api_thread = threading.Thread(target=start_api_gateway)
            self.api_thread.daemon = True
            self.api_thread.start()
            
            # Wait for API to be ready
            time.sleep(2)
            
            # Open web UI
            from CAMF.common.config import env_config
            print("Opening web interface...")
            webbrowser.open(f"http://localhost:{env_config.api_port}")
            
            self.running = True
            print("\nCAMF is running! Press Ctrl+C to stop.")
            
            # Keep running
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nShutdown requested...")
            self.stop()
        except Exception as e:
            print(f"Failed to start CAMF: {e}")
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Stop all services."""
        print("Stopping CAMF services...")
        self.running = False
        
        # Stop services in reverse order
        if 'detector_framework' in self.services:
            self.services['detector_framework'].cleanup()
        
        if 'capture' in self.services:
            self.services['capture'].cleanup()
        
        # Storage service doesn't have cleanup method - uses connection pooling
        # if 'storage' in self.services:
        #     self.services['storage'].cleanup()
        
        print("CAMF stopped.")


def main():
    """Main entry point."""
    # Set up signal handlers
    app = CAMFApplication()
    
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        app.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start application
    app.start()


if __name__ == "__main__":
    main()