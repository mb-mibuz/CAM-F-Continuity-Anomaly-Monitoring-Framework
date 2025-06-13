# window.py - Fixed version
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
import platform
import ctypes
from ctypes import wintypes

from .source import CaptureSource

class WindowSource(CaptureSource):
    """Enhanced window-based capture source that works with minimized/occluded windows."""
    
    def __init__(self, window_handle=None, frame_rate=24, max_resolution=None):
        """Initialize a window source.
        
        Args:
            window_handle: Handle of the window to capture
            frame_rate: Frames per second to capture
            max_resolution: Maximum resolution as (width, height) or None
        """
        # Initialize parent class
        super().__init__(frame_rate, max_resolution)
        self.window_handle = window_handle
        self.window_info = None
        self._capture_method = None
        # Set name after initialization
        self.name = f"Window {window_handle}"
        
        # Check platform and use cross-platform implementation if not Windows
        if platform.system() != "Windows":
            # Import and use cross-platform implementation
            from .window_cross_platform import WindowSource as CrossPlatformWindowSource
            # Replace this instance with cross-platform version
            self.__class__ = CrossPlatformWindowSource
            self.__init__(window_handle, frame_rate, max_resolution)
            return
        
        # Import Windows-specific libraries
        try:
            import win32gui
            import win32ui
            import win32con
            import win32api
            self.win32gui = win32gui
            self.win32ui = win32ui
            self.win32con = win32con
            self.win32api = win32api
        except ImportError:
            raise ImportError("pywin32 is required for window capture. Install with: pip install pywin32")
        
        # Set up ctypes for advanced capture methods
        self._setup_ctypes()
    
    def _setup_ctypes(self):
        """Set up ctypes for advanced Windows APIs."""
        self.user32 = ctypes.windll.user32
        self.dwmapi = ctypes.windll.dwmapi
        
        # PrintWindow flags
        self.PW_RENDERFULLCONTENT = 0x00000002  # Introduced in Windows 8.1
        
        # DWM thumbnail constants
        self.DWM_TNP_VISIBLE = 0x8
        self.DWM_TNP_RECTDESTINATION = 0x1
        self.DWM_TNP_RECTSOURCE = 0x2
        self.DWM_TNP_SOURCECLIENTAREAONLY = 0x10
        
        # Structures for DWM
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long),
                       ("top", ctypes.c_long),
                       ("right", ctypes.c_long),
                       ("bottom", ctypes.c_long)]
        
        class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
            _fields_ = [("dwFlags", wintypes.DWORD),
                       ("rcDestination", RECT),
                       ("rcSource", RECT),
                       ("opacity", ctypes.c_ubyte),
                       ("fVisible", wintypes.BOOL),
                       ("fSourceClientAreaOnly", wintypes.BOOL)]
        
        self.RECT = RECT
        self.DWM_THUMBNAIL_PROPERTIES = DWM_THUMBNAIL_PROPERTIES
    
    def connect(self) -> bool:
        """Connect to the window source."""
        try:
            # Verify window exists
            if not self.win32gui.IsWindow(self.window_handle):
                print(f"Window handle {self.window_handle} is not valid")
                return False
            
            # Get window info
            rect = self.win32gui.GetWindowRect(self.window_handle)
            client_rect = self.win32gui.GetClientRect(self.window_handle)
            
            # Calculate actual window size (including non-client area)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            # Get client area size
            client_width = client_rect[2]
            client_height = client_rect[3]
            
            if width <= 0 or height <= 0:
                print(f"Window has invalid dimensions: {width}x{height}")
                return False
            
            # Check if window is minimized
            placement = self.win32gui.GetWindowPlacement(self.window_handle)
            is_minimized = placement[1] == self.win32con.SW_SHOWMINIMIZED
            
            # Get window title and class for debugging
            window_title = self.win32gui.GetWindowText(self.window_handle)
            window_class = self.win32gui.GetClassName(self.window_handle)
            
            self.window_info = {
                "handle": self.window_handle,
                "rect": rect,
                "client_rect": client_rect,
                "width": width,
                "height": height,
                "client_width": client_width,
                "client_height": client_height,
                "is_minimized": is_minimized,
                "title": window_title,
                "class": window_class,
                "use_client_area": True  # Default to capturing client area only
            }
            
            # Update the source name with the window title
            self.name = window_title or f"Window {self.window_handle}"
            
            # Determine best capture method
            self._determine_capture_method()
            
            print(f"Connected to window: {window_title} (Method: {self._capture_method})")
            return True
            
        except Exception as e:
            print(f"Error connecting to window: {e}")
            self.window_info = None
            return False
    
    def _determine_capture_method(self):
        """Determine the best capture method for this window."""
        # For now, use PrintWindow as the primary method
        # This works for most windows including minimized ones
        self._capture_method = "printwindow"
    
    def disconnect(self):
        """Disconnect from the window source."""
        self.stop_capture()
        self.window_info = None
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the window.
        
        Returns:
            Frame as numpy array or None if capture failed
        """
        if not self.window_info:
            return None
        
        # Check if window still exists
        try:
            if not self.win32gui.IsWindow(self.window_handle):
                print(f"Window {self.window_handle} no longer exists")
                return None
        except Exception as e:
            print(f"Error checking window existence: {e}")
            return None
        
        # Update window state
        try:
            placement = self.win32gui.GetWindowPlacement(self.window_handle)
            self.window_info["is_minimized"] = placement[1] == self.win32con.SW_SHOWMINIMIZED
        except Exception as e:
            print(f"Error getting window placement: {e}")
            return None
        
        # Try PrintWindow method first (works for minimized/occluded windows)
        frame = self._capture_with_printwindow_client_area()
        
        # If PrintWindow failed or returned black frame, try BitBlt as fallback
        if frame is None or self._is_black_frame(frame):
            frame = self._capture_with_bitblt_client_area()
        
        return frame
    
    def _capture_with_printwindow(self) -> Optional[np.ndarray]:
        """Capture using PrintWindow API (works with minimized/occluded windows)."""
        try:
            hwnd = self.window_info["handle"]
            
            # Get window dimensions
            rect = self.win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                return None
            
            # Create device contexts
            hwndDC = self.win32gui.GetWindowDC(hwnd)
            mfcDC = self.win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Create bitmap
            saveBitMap = self.win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Fill with white background first (helps detect if PrintWindow worked)
            saveDC.FillSolidRect((0, 0, width, height), 0xFFFFFF)
            
            # Use PrintWindow to capture the window
            # PW_RENDERFULLCONTENT flag captures the full window including parts that are occluded
            result = self.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), self.PW_RENDERFULLCONTENT)
            
            if result == 0:
                # PrintWindow failed
                self.win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                self.win32gui.ReleaseDC(hwnd, hwndDC)
                return None
            
            # Convert to numpy array
            signedIntsArray = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (height, width, 4)
            
            # Convert from BGRA to BGR
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Clean up
            self.win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            self.win32gui.ReleaseDC(hwnd, hwndDC)
            
            return frame
            
        except Exception as e:
            print(f"Error in PrintWindow capture: {e}")
            return None
    
    def _capture_with_bitblt(self) -> Optional[np.ndarray]:
        """Capture using BitBlt (fallback method for visible windows)."""
        if self.window_info["is_minimized"]:
            # BitBlt doesn't work for minimized windows
            return None
        
        try:
            hwnd = self.window_info["handle"]
            left, top, right, bottom = self.window_info["rect"]
            width = right - left
            height = bottom - top
            
            # Create device context
            wDC = self.win32gui.GetWindowDC(hwnd)
            dcObj = self.win32ui.CreateDCFromHandle(wDC)
            cDC = dcObj.CreateCompatibleDC()
            
            # Create bitmap
            dataBitMap = self.win32ui.CreateBitmap()
            dataBitMap.CreateCompatibleBitmap(dcObj, width, height)
            cDC.SelectObject(dataBitMap)
            
            # Copy window content to bitmap
            cDC.BitBlt((0, 0), (width, height), dcObj, (0, 0), self.win32con.SRCCOPY)
            
            # Convert to numpy array
            signedIntsArray = dataBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (height, width, 4)
            
            # Convert from BGRA to BGR
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Clean up
            dcObj.DeleteDC()
            cDC.DeleteDC()
            self.win32gui.ReleaseDC(hwnd, wDC)
            self.win32gui.DeleteObject(dataBitMap.GetHandle())
            
            return frame
            
        except Exception as e:
            print(f"Error in BitBlt capture: {e}")
            return None
    
    def _capture_with_printwindow_client_area(self) -> Optional[np.ndarray]:
        """Capture only the client area using PrintWindow API."""
        try:
            hwnd = self.window_info["handle"]
            
            # Get client area dimensions
            client_rect = self.win32gui.GetClientRect(hwnd)
            width = client_rect[2]
            height = client_rect[3]
            
            if width <= 0 or height <= 0:
                return None
            
            # Create device contexts
            hwndDC = self.win32gui.GetWindowDC(hwnd)
            mfcDC = self.win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Create bitmap for client area size
            saveBitMap = self.win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Fill with white background first
            saveDC.FillSolidRect((0, 0, width, height), 0xFFFFFF)
            
            # Use PrintWindow with PW_CLIENTONLY flag if available
            PW_CLIENTONLY = 0x00000001
            result = self.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), self.PW_RENDERFULLCONTENT | PW_CLIENTONLY)
            
            if result == 0:
                # PrintWindow failed
                self.win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                self.win32gui.ReleaseDC(hwnd, hwndDC)
                return None
            
            # Convert to numpy array
            signedIntsArray = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (height, width, 4)
            
            # Convert from BGRA to BGR
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Clean up
            self.win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            self.win32gui.ReleaseDC(hwnd, hwndDC)
            
            return frame
            
        except Exception as e:
            print(f"Error in PrintWindow client area capture: {e}")
            # Fall back to full window capture
            return self._capture_with_printwindow()
    
    def _capture_with_bitblt_client_area(self) -> Optional[np.ndarray]:
        """Capture only the client area using BitBlt."""
        if self.window_info["is_minimized"]:
            return None
        
        try:
            hwnd = self.window_info["handle"]
            
            # Get client area dimensions
            client_rect = self.win32gui.GetClientRect(hwnd)
            width = client_rect[2]
            height = client_rect[3]
            
            if width <= 0 or height <= 0:
                return None
            
            # Get the client area device context
            clientDC = self.win32gui.GetDC(hwnd)  # GetDC gets client area DC
            dcObj = self.win32ui.CreateDCFromHandle(clientDC)
            cDC = dcObj.CreateCompatibleDC()
            
            # Create bitmap
            dataBitMap = self.win32ui.CreateBitmap()
            dataBitMap.CreateCompatibleBitmap(dcObj, width, height)
            cDC.SelectObject(dataBitMap)
            
            # Copy client area content to bitmap
            cDC.BitBlt((0, 0), (width, height), dcObj, (0, 0), self.win32con.SRCCOPY)
            
            # Convert to numpy array
            signedIntsArray = dataBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (height, width, 4)
            
            # Convert from BGRA to BGR
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Clean up
            dcObj.DeleteDC()
            cDC.DeleteDC()
            self.win32gui.ReleaseDC(hwnd, clientDC)
            self.win32gui.DeleteObject(dataBitMap.GetHandle())
            
            return frame
            
        except Exception as e:
            print(f"Error in BitBlt client area capture: {e}")
            # Fall back to full window capture
            return self._capture_with_bitblt()
    
    def _is_black_frame(self, frame: np.ndarray) -> bool:
        """Check if a frame is completely black (failed capture)."""
        if frame is None:
            return True
        
        # Calculate mean brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        mean_brightness = np.mean(gray)
        
        # If mean brightness is very low, it's likely a black frame
        return mean_brightness < 5
    
    @staticmethod
    def list_windows() -> List[Dict[str, Any]]:
        """List available windows on the system with enhanced metadata."""
        if platform.system() != "Windows":
            return []
        
        try:
            import win32gui
            import win32process
            import win32api
            import win32con

            PROBLEMATIC_HANDLES = {66884}
            
            # System window classes to exclude
            EXCLUDED_CLASSES = {
                'Progman',  # Program Manager (Desktop)
                'WorkerW',  # Desktop worker window
                'Shell_TrayWnd',  # Taskbar
                'Shell_SecondaryTrayWnd',  # Secondary taskbar
                'Windows.UI.Core.CoreWindow',  # UWP system windows
                'ApplicationFrameWindow',  # UWP frame (unless it has a real app)
                'Windows.Internal.Shell.TabProxyWindow',  # Virtual desktop
                'ForegroundStaging',  # Staging windows
                'ApplicationManager_DesktopShellWindow',  # Shell windows
                'Static',  # Static controls
                'Scrollbar',  # Scrollbars
                'tooltips_class32',  # Tooltips
                'msctls_statusbar32',  # Status bars
                'Button',  # Buttons
                'SysListView32',  # List views (unless main window)
                'SysTreeView32',  # Tree views (unless main window)
                'DirectUIHWND',  # DirectUI windows
                'CtrlNotifySink',  # Notification sinks
                'MSCTFIME UI',  # IME windows
                'IME',  # Input method windows
            }
            
            # System process names to exclude
            EXCLUDED_PROCESSES = {
                'textinputhost.exe',  # Windows Input Experience
                'searchhost.exe',  # Windows Search
                'searchapp.exe',  # Windows Search App
                'shellexperiencehost.exe',  # Shell Experience Host
                'systemsettings.exe',  # Settings app (usually not needed)
                'lockapp.exe',  # Lock screen
                'peopleapp.exe',  # People app
                'video.ui.exe',  # Video app
                'gamebar.exe',  # Game bar
                'gamebarftserver.exe',  # Game bar
                'applicationframehost.exe',  # UWP host (check if it has real content)
                'dwm.exe',  # Desktop Window Manager
                'sihost.exe',  # Shell Infrastructure Host
                'fontdrvhost.exe',  # Font driver
                'winlogon.exe',  # Windows logon
                'csrss.exe',  # Client/Server Runtime
                'smss.exe',  # Session Manager
                'wininit.exe',  # Windows Init
                'services.exe',  # Services
                'lsass.exe',  # Local Security Authority
                'svchost.exe',  # Service Host
                'taskhostw.exe',  # Task Host
                'dllhost.exe',  # DLL Host
                'conhost.exe',  # Console Host
                'ctfmon.exe',  # CTF Loader
                'runtimebroker.exe',  # Runtime Broker
                'settingssynchost.exe',  # Settings Sync
                'systemsettingsbroker.exe',  # System Settings Broker
                'usernotificationapp.exe',  # Notifications
                'comp integratorshell.exe',  # Comp Integrator
                'startmenuexperiencehost.exe',  # Start Menu
                'windows.internal.composableshell.experiences.textinput.inputapp.exe',  # Input app
                'msedgewebview2.exe',  # Edge WebView (unless main window)
            }
            
            # NVIDIA and GPU overlay processes
            EXCLUDED_PROCESSES.update({
                'nvcontainer.exe',
                'nvidia share.exe',
                'nvsphelper64.exe',
                'nvspcaps64.exe',
                'nvtelemetrycontainer.exe',
                'nvofficialoverlay.exe',
                'nvoverlaysupport.exe',
                'geforce experience.exe',
                'geforcenow.exe',
                'nvbackend.exe',
                'nvdisplay.container.exe',
                'nvcamera.exe',
                'nvidia web helper.exe',
            })
            
            # Window title patterns to exclude
            EXCLUDED_TITLES = {
                'default ime',
                'nvidia geforce overlay',
                'program manager',
                'windows input experience',
                'microsoft text input application',
                'settings',
                'movies & tv',
                'cortana',
                'meet now',
                'microsoft store',
                'xbox game bar',
                'game bar',
                'nvidia overlay',
                'geforce experience',
                'nvidia share',
                'drag',  # Drag and drop helpers
                'tooltip',
                'msctfime ui',
                'task switching',
            }
            
            def should_exclude_window(hwnd, title, window_class, process_name):
                """Determine if a window should be excluded from the list."""
                # Convert to lowercase for comparison
                title_lower = title.lower()
                class_lower = window_class.lower()
                process_lower = process_name.lower()
                
                # Check excluded classes
                if window_class in EXCLUDED_CLASSES:
                    return True
                
                # Check excluded processes
                if process_lower in EXCLUDED_PROCESSES:
                    return True
                
                # Check excluded title patterns
                for excluded in EXCLUDED_TITLES:
                    if excluded in title_lower:
                        return True
                
                # Special case: ApplicationFrameWindow might contain real apps
                if window_class == 'ApplicationFrameWindow':
                    # If it has a meaningful title and isn't a system app, include it
                    if title and not any(excluded in title_lower for excluded in EXCLUDED_TITLES):
                        return False
                    return True
                
                # Exclude windows with no title (with some exceptions)
                if not title and window_class not in ['CabinetWClass', 'ExploreWClass']:  # Explorer windows
                    return True
                
                # Exclude NVIDIA overlay windows by class pattern
                if 'nvidia' in class_lower or 'nvcontainer' in class_lower:
                    return True
                
                # Exclude various overlay and notification windows
                if any(x in class_lower for x in ['overlay', 'tooltip', 'notification', 'banner']):
                    return True
                
                return False
            
            def get_window_process_name(hwnd):
                """Get the process name for a window."""
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    handle = win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False, pid
                    )
                    exe_name = win32process.GetModuleFileNameEx(handle, 0)
                    win32api.CloseHandle(handle)
                    return exe_name.split('\\')[-1]  # Just the filename
                except:
                    return "Unknown"
                
            def is_valid_window(hwnd, title, window_class):
                """Additional validation for windows."""
                # Skip known problematic handles
                if hwnd in PROBLEMATIC_HANDLES:
                    return False
                    
                # Skip windows with empty titles and certain classes
                if not title and window_class in ['Static', 'msctls_statusbar32']:
                    return False
                    
                return True
            
            def callback(hwnd, windows):
                try:
                    if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindow(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        window_class = win32gui.GetClassName(hwnd)
                        process_name = get_window_process_name(hwnd)
                        
                        # Apply exclusion rules
                        if should_exclude_window(hwnd, title, window_class, process_name):
                            return True
                        
                        # Additional validation
                        if not is_valid_window(hwnd, title, window_class):
                            return True
                        
                        # Try to get window rect
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            width = rect[2] - rect[0]
                            height = rect[3] - rect[1]
                            
                            # Skip windows with invalid dimensions
                            if width <= 0 or height <= 0:
                                return True
                                
                        except Exception:
                            return True
                        
                        # Get window placement
                        try:
                            placement = win32gui.GetWindowPlacement(hwnd)
                            is_minimized = placement[1] == win32con.SW_SHOWMINIMIZED
                        except Exception:
                            is_minimized = False
                        
                        # Only include windows with reasonable dimensions or if minimized
                        if (width > 100 and height > 100) or is_minimized:
                            windows.append({
                                "handle": hwnd,
                                "title": title or f"Window {hwnd}",
                                "resolution": (width, height),
                                "is_minimized": is_minimized,
                                "window_class": window_class,
                                "process_name": process_name
                            })
                except Exception as e:
                    print(f"Error processing window {hwnd}: {e}")
                return True
            
            windows = []
            win32gui.EnumWindows(callback, windows)
            
            # Sort by process name and title for better organization
            windows.sort(key=lambda w: (w["process_name"], w["title"]))
            
            return windows
            
        except Exception as e:
            print(f"Error listing windows: {e}")
            return []