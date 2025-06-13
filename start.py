#!/usr/bin/env python
"""
Development startup script for CAMF
Starts both backend and frontend services
"""

import subprocess
import sys
import os
import time
import signal
import socket
import shutil
import webbrowser

# Store process references for cleanup
processes = []

def cleanup(signum=None, frame=None):
    """Clean up all running processes"""
    print("\nShutting down CAMF...")
    for process in processes:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            try:
                process.kill()
            except:
                pass
    sys.exit(0)

# Register cleanup handlers
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def check_port(port):
    """Check if a port is available"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True
    except:
        return False

def wait_for_port(port, timeout=30):
    """Wait for a port to become active"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(('127.0.0.1', port))
            sock.close()
            return True
        except:
            time.sleep(0.5)
    return False

def check_npm():
    """Check if npm is installed"""
    return shutil.which('npm') is not None

def check_rust():
    """Check if Rust is installed"""
    return shutil.which('cargo') is not None

def kill_process_on_port(port):
    """Kill process using the specified port"""
    if sys.platform == "win32":
        try:
            # Windows
            result = subprocess.run(
                f'netstat -ano | findstr :{port}', 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        pid = parts[-1]
                        print(f"Found process {pid} using port {port}")
                        subprocess.run(f'taskkill /PID {pid} /F', shell=True)
                        time.sleep(1)
                        return True
        except Exception as e:
            print(f"Error killing process on port {port}: {e}")
    else:
        try:
            # Unix-like systems
            result = subprocess.run(
                f'lsof -ti:{port}', 
                shell=True, 
                capture_output=True, 
                text=True
            )
            if result.stdout:
                pid = result.stdout.strip()
                print(f"Found process {pid} using port {port}")
                subprocess.run(f'kill -9 {pid}', shell=True)
                time.sleep(1)
                return True
        except Exception as e:
            print(f"Error killing process on port {port}: {e}")
    return False

def run_backend():
    """Start the backend service"""
    print("Starting CAMF backend...")
    
    # Check if port 8000 is available
    if not check_port(8000):
        print("Port 8000 is already in use!")
        response = input("Do you want to kill the existing process? (y/n): ")
        if response.lower() == 'y':
            if kill_process_on_port(8000):
                print("Killed existing process on port 8000")
                time.sleep(2)
            else:
                print("Failed to kill process. Please manually stop the process using port 8000.")
                return None
        else:
            print("Please stop the existing process on port 8000 and try again.")
            return None
    
    # Start backend
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "CAMF.launcher"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    processes.append(backend_process)
    
    # Wait for backend to be ready
    print("Waiting for backend to start...")
    if wait_for_port(8000):
        print("Backend started successfully on port 8000")
    else:
        print("Backend failed to start within timeout period")
        return None
    
    return backend_process

def run_frontend():
    """Start the frontend with Tauri"""
    print("\nStarting CAMF frontend...")
    
    # Check dependencies
    if not check_npm():
        print("\nERROR: npm is not installed!")
        print("Please install Node.js from: https://nodejs.org/")
        return None
    
    if not check_rust():
        print("\nERROR: Rust is not installed!")
        print("Please install Rust from: https://rustup.rs/")
        return None
    
    # Get frontend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(script_dir, "CAMF", "frontend")
    
    if not os.path.exists(frontend_dir):
        print(f"\nERROR: Frontend directory not found: {frontend_dir}")
        return None
    
    # Check for node_modules
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("Installing frontend dependencies...")
        try:
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True, shell=True)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to install dependencies: {e}")
            return None
    
    # Kill any existing processes on Vite port
    if not check_port(5173):
        print("Port 5173 is in use, killing existing process...")
        kill_process_on_port(5173)
        time.sleep(2)
    
    # Set environment variable to suppress browser opening
    env = os.environ.copy()
    env['BROWSER'] = 'none'
    
    # Start Tauri in development mode
    print("Starting Tauri development server...")
    try:
        frontend_process = subprocess.Popen(
            ["npm", "run", "tauri", "dev"],
            cwd=frontend_dir,
            shell=True,
            env=env
        )
        processes.append(frontend_process)
        
        # Give Tauri time to start
        print("Waiting for Tauri to initialize...")
        time.sleep(5)
        
        return frontend_process
    except Exception as e:
        print(f"ERROR: Failed to start frontend: {e}")
        return None

def main():
    """Main entry point"""
    print("=" * 50)
    print("CAMF Development Environment")
    print("=" * 50)
    
    # Start backend
    backend = run_backend()
    if not backend:
        print("\nFailed to start backend. Exiting...")
        cleanup()
        return
    
    # Start frontend
    frontend = run_frontend()
    if not frontend:
        print("\nFailed to start frontend.")
        print("Backend is still running at: http://127.0.0.1:8000")
        print("\nTo manually start frontend:")
        print("  cd CAMF/frontend")
        print("  npm install")
        print("  npm run tauri dev")
    else:
        print("\n" + "=" * 50)
        print("CAMF is running!")
        print("Backend API: http://127.0.0.1:8000")
        print("Frontend should open in a Tauri window")
        print("\nIf the window is white, press F12 for developer tools")
        print("=" * 50)
    
    print("\nPress Ctrl+C to stop all services\n")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
            # Check if processes are still running
            if backend and backend.poll() is not None:
                print("\nBackend process terminated unexpectedly!")
                break
            if frontend and frontend.poll() is not None:
                print("\nFrontend process terminated unexpectedly!")
                break
    except KeyboardInterrupt:
        pass
    
    cleanup()

if __name__ == "__main__":
    main()