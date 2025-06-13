# window_cross_platform.py - Cross-platform window capture implementation
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
import platform
import logging

from .source import CaptureSource

logger = logging.getLogger(__name__)


class WindowSource(CaptureSource):
    """Cross-platform window-based capture source."""
    
    def __init__(self, window_handle=None, frame_rate=24, max_resolution=None):
        """Initialize a window source.
        
        Args:
            window_handle: Handle/ID of the window to capture
            frame_rate: Frames per second to capture
            max_resolution: Maximum resolution as (width, height) or None
        """
        super().__init__(frame_rate, max_resolution)
        self.window_handle = window_handle
        self.window_info = None
        self._capture_method = None
        self.name = f"Window {window_handle}"
        
        # Platform-specific initialization
        self.platform = platform.system()
        self._platform_initialized = False
        
        # Platform-specific modules
        self._platform_modules = {}
        
        if self.platform == "Windows":
            self._init_windows()
        elif self.platform == "Linux":
            self._init_linux()
        elif self.platform == "Darwin":  # macOS
            self._init_macos()
        else:
            raise NotImplementedError(f"Window capture not implemented for {self.platform}")
    
    def _init_windows(self):
        """Initialize Windows-specific capture."""
        try:
            import win32gui
            import win32ui
            import win32con
            import win32api
            import ctypes
            
            self._platform_modules['win32gui'] = win32gui
            self._platform_modules['win32ui'] = win32ui
            self._platform_modules['win32con'] = win32con
            self._platform_modules['win32api'] = win32api
            self._platform_modules['ctypes'] = ctypes
            
            # Set up ctypes for advanced APIs
            self.user32 = ctypes.windll.user32
            self.PW_RENDERFULLCONTENT = 0x00000002
            
            self._platform_initialized = True
            self._capture_method = "windows_printwindow"
            
        except ImportError as e:
            logger.error(f"Windows modules not available: {e}")
            logger.info("Install pywin32: pip install pywin32")
            raise ImportError("pywin32 is required for window capture on Windows")
    
    def _init_linux(self):
        """Initialize Linux-specific capture using X11."""
        try:
            # Try to import X11 libraries
            from Xlib import display, X
            from Xlib.ext import composite
            import PIL.Image as PILImage
            
            self._platform_modules['display'] = display
            self._platform_modules['X'] = X
            self._platform_modules['composite'] = composite
            self._platform_modules['PILImage'] = PILImage
            
            # Initialize X11 display
            self.display = display.Display()
            self.root = self.display.screen().root
            
            # Check for composite extension (needed for window capture)
            if not self.display.has_extension("Composite"):
                raise RuntimeError("X11 Composite extension not available")
            
            self._platform_initialized = True
            self._capture_method = "x11_composite"
            
        except ImportError as e:
            logger.error(f"X11 libraries not available: {e}")
            logger.info("Install python-xlib: pip install python-xlib pillow")
            # Try alternative method using mss
            try:
                import mss
                self._platform_modules['mss'] = mss
                self._platform_initialized = True
                self._capture_method = "mss_fallback"
                logger.info("Using mss as fallback for Linux window capture")
            except ImportError:
                raise ImportError("python-xlib or mss is required for window capture on Linux")
    
    def _init_macos(self):
        """Initialize macOS-specific capture."""
        try:
            # Try to import Quartz (pyobjc-framework-Quartz)
            import Quartz
            import AppKit
            
            self._platform_modules['Quartz'] = Quartz
            self._platform_modules['AppKit'] = AppKit
            
            self._platform_initialized = True
            self._capture_method = "quartz_window"
            
        except ImportError as e:
            logger.error(f"macOS frameworks not available: {e}")
            logger.info("Install pyobjc: pip install pyobjc-framework-Quartz pyobjc-framework-AppKit")
            # Try alternative method using mss
            try:
                import mss
                self._platform_modules['mss'] = mss
                self._platform_initialized = True
                self._capture_method = "mss_fallback"
                logger.info("Using mss as fallback for macOS window capture")
            except ImportError:
                raise ImportError("pyobjc or mss is required for window capture on macOS")
    
    def connect(self) -> bool:
        """Connect to the window source."""
        if not self._platform_initialized:
            return False
        
        try:
            if self.platform == "Windows":
                return self._connect_windows()
            elif self.platform == "Linux":
                return self._connect_linux()
            elif self.platform == "Darwin":
                return self._connect_macos()
            else:
                return False
        except Exception as e:
            logger.error(f"Error connecting to window: {e}")
            return False
    
    def _connect_windows(self) -> bool:
        """Windows-specific connection."""
        win32gui = self._platform_modules['win32gui']
        win32con = self._platform_modules['win32con']
        
        # Verify window exists
        if not win32gui.IsWindow(self.window_handle):
            logger.error(f"Window handle {self.window_handle} is not valid")
            return False
        
        # Get window info
        rect = win32gui.GetWindowRect(self.window_handle)
        win32gui.GetClientRect(self.window_handle)
        
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        if width <= 0 or height <= 0:
            logger.error(f"Window has invalid dimensions: {width}x{height}")
            return False
        
        # Check if minimized
        placement = win32gui.GetWindowPlacement(self.window_handle)
        is_minimized = placement[1] == win32con.SW_SHOWMINIMIZED
        
        # Get window title
        window_title = win32gui.GetWindowText(self.window_handle)
        window_class = win32gui.GetClassName(self.window_handle)
        
        self.window_info = {
            "handle": self.window_handle,
            "rect": rect,
            "width": width,
            "height": height,
            "is_minimized": is_minimized,
            "title": window_title,
            "class": window_class
        }
        
        self.name = window_title or f"Window {self.window_handle}"
        logger.info(f"Connected to window: {window_title}")
        return True
    
    def _connect_linux(self) -> bool:
        """Linux-specific connection."""
        if self._capture_method == "mss_fallback":
            # For mss, we need window geometry
            # This is a simplified version - real implementation would use window manager APIs
            self.window_info = {
                "handle": self.window_handle,
                "title": f"Window {self.window_handle}"
            }
            self.name = f"Window {self.window_handle}"
            return True
        
        # X11 implementation
        try:
            # Get window from handle (assuming it's an X11 window ID)
            window = self.display.create_resource_object('window', self.window_handle)
            
            # Get window geometry
            geom = window.get_geometry()
            window.get_attributes()
            
            self.window_info = {
                "handle": self.window_handle,
                "window": window,
                "width": geom.width,
                "height": geom.height,
                "x": geom.x,
                "y": geom.y
            }
            
            # Try to get window name
            try:
                name = window.get_wm_name()
                self.name = name or f"Window {self.window_handle}"
                self.window_info["title"] = name
            except:
                self.name = f"Window {self.window_handle}"
            
            logger.info(f"Connected to X11 window: {self.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to X11 window: {e}")
            return False
    
    def _connect_macos(self) -> bool:
        """macOS-specific connection."""
        if self._capture_method == "mss_fallback":
            # For mss, we need window geometry
            self.window_info = {
                "handle": self.window_handle,
                "title": f"Window {self.window_handle}"
            }
            self.name = f"Window {self.window_handle}"
            return True
        
        # Quartz implementation
        Quartz = self._platform_modules['Quartz']
        
        # Get window info using CGWindowListCopyWindowInfo
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow,
            self.window_handle
        )
        
        if not window_list or len(window_list) == 0:
            logger.error(f"Window {self.window_handle} not found")
            return False
        
        window_info = window_list[0]
        bounds = window_info.get(Quartz.kCGWindowBounds, {})
        
        self.window_info = {
            "handle": self.window_handle,
            "title": window_info.get(Quartz.kCGWindowName, f"Window {self.window_handle}"),
            "owner": window_info.get(Quartz.kCGWindowOwnerName, "Unknown"),
            "width": int(bounds.get('Width', 0)),
            "height": int(bounds.get('Height', 0)),
            "x": int(bounds.get('X', 0)),
            "y": int(bounds.get('Y', 0))
        }
        
        self.name = self.window_info["title"]
        logger.info(f"Connected to macOS window: {self.name}")
        return True
    
    def disconnect(self):
        """Disconnect from the window source."""
        self.stop_capture()
        self.window_info = None
        
        if self.platform == "Linux" and hasattr(self, 'display'):
            try:
                self.display.close()
            except:
                pass
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the window."""
        if not self.window_info:
            return None
        
        try:
            if self.platform == "Windows":
                return self._capture_windows()
            elif self.platform == "Linux":
                return self._capture_linux()
            elif self.platform == "Darwin":
                return self._capture_macos()
            else:
                return None
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return None
    
    def _capture_windows(self) -> Optional[np.ndarray]:
        """Windows-specific capture using PrintWindow."""
        win32gui = self._platform_modules['win32gui']
        win32ui = self._platform_modules['win32ui']
        
        hwnd = self.window_info["handle"]
        width = self.window_info["width"]
        height = self.window_info["height"]
        
        try:
            # Create device contexts
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Create bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Use PrintWindow
            result = self.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), self.PW_RENDERFULLCONTENT)
            
            if result == 0:
                raise RuntimeError("PrintWindow failed")
            
            # Convert to numpy array
            signedIntsArray = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (height, width, 4)
            
            # Convert BGRA to BGR
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # Cleanup
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            
            return frame
            
        except Exception as e:
            logger.error(f"Windows capture error: {e}")
            return None
    
    def _capture_linux(self) -> Optional[np.ndarray]:
        """Linux-specific capture."""
        if self._capture_method == "mss_fallback":
            return self._capture_mss()
        
        # X11 composite capture
        try:
            self._platform_modules['composite']
            PILImage = self._platform_modules['PILImage']
            
            window = self.window_info["window"]
            width = self.window_info["width"]
            height = self.window_info["height"]
            
            # Get pixmap of the window
            pixmap = window.composite_name_window_pixmap()
            
            # Get image from pixmap
            raw_image = pixmap.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
            
            # Convert to PIL Image
            pil_image = PILImage.frombytes("RGB", (width, height), raw_image.data, "raw", "BGRX")
            
            # Convert to numpy array
            frame = np.array(pil_image)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            return frame
            
        except Exception as e:
            logger.error(f"X11 capture error: {e}")
            return None
    
    def _capture_macos(self) -> Optional[np.ndarray]:
        """macOS-specific capture."""
        if self._capture_method == "mss_fallback":
            return self._capture_mss()
        
        # Quartz window capture
        try:
            Quartz = self._platform_modules['Quartz']
            
            # Create window image
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull,
                Quartz.kCGWindowListOptionIncludingWindow,
                self.window_handle,
                Quartz.kCGWindowImageDefault
            )
            
            if not image:
                raise RuntimeError("Failed to create window image")
            
            # Get image data
            width = Quartz.CGImageGetWidth(image)
            height = Quartz.CGImageGetHeight(image)
            bytes_per_row = Quartz.CGImageGetBytesPerRow(image)
            
            # Create bitmap context
            color_space = Quartz.CGColorSpaceCreateDeviceRGB()
            bitmap_info = Quartz.kCGBitmapByteOrder32Big | Quartz.kCGImageAlphaPremultipliedLast
            
            context = Quartz.CGBitmapContextCreate(
                None, width, height, 8, bytes_per_row, color_space, bitmap_info
            )
            
            # Draw image to context
            Quartz.CGContextDrawImage(context, ((0, 0), (width, height)), image)
            
            # Get pixel data
            pixel_data = Quartz.CGBitmapContextGetData(context)
            
            # Convert to numpy array
            buffer_size = height * bytes_per_row
            if pixel_data:
                import ctypes
                buffer = ctypes.string_at(pixel_data, buffer_size)
                frame = np.frombuffer(buffer, dtype=np.uint8)
                frame = frame.reshape((height, width, 4))
                # Convert RGBA to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                return frame
            
            return None
            
        except Exception as e:
            logger.error(f"macOS capture error: {e}")
            return None
    
    def _capture_mss(self) -> Optional[np.ndarray]:
        """Fallback capture using mss (screen capture library)."""
        # This is a simplified implementation
        # In practice, you'd need to get window geometry from the window manager
        logger.warning("Using mss fallback - capturing full screen instead of specific window")
        
        try:
            mss = self._platform_modules['mss']
            
            with mss.mss() as sct:
                # For now, capture the entire primary monitor
                # Real implementation would get window bounds
                monitor = sct.monitors[1]  # Primary monitor
                
                # Capture
                screenshot = sct.grab(monitor)
                
                # Convert to numpy array
                frame = np.array(screenshot)
                # mss returns BGRA, convert to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                return frame
                
        except Exception as e:
            logger.error(f"mss capture error: {e}")
            return None
    
    @staticmethod
    def list_windows() -> List[Dict[str, Any]]:
        """List available windows on the system."""
        platform_name = platform.system()
        
        if platform_name == "Windows":
            return WindowSource._list_windows_windows()
        elif platform_name == "Linux":
            return WindowSource._list_windows_linux()
        elif platform_name == "Darwin":
            return WindowSource._list_windows_macos()
        else:
            return []
    
    @staticmethod
    def _list_windows_windows() -> List[Dict[str, Any]]:
        """List windows on Windows - delegates to original implementation."""
        # Import the original Windows implementation
        from . import window as window_windows
        return window_windows.WindowSource.list_windows()
    
    @staticmethod
    def _list_windows_linux() -> List[Dict[str, Any]]:
        """List windows on Linux using X11."""
        windows = []
        
        try:
            from Xlib import display, X
            
            d = display.Display()
            root = d.screen().root
            
            def get_window_name(window):
                try:
                    name = window.get_wm_name()
                    return name if name else "Unnamed"
                except:
                    return "Unnamed"
            
            def get_window_class(window):
                try:
                    wm_class = window.get_wm_class()
                    if wm_class:
                        return wm_class[1] if len(wm_class) > 1 else wm_class[0]
                    return "Unknown"
                except:
                    return "Unknown"
            
            def enum_windows(window):
                try:
                    attrs = window.get_attributes()
                    if attrs.map_state == X.IsViewable:
                        geom = window.get_geometry()
                        
                        # Skip small windows
                        if geom.width > 50 and geom.height > 50:
                            name = get_window_name(window)
                            wm_class = get_window_class(window)
                            
                            windows.append({
                                "handle": window.id,
                                "title": name,
                                "resolution": (geom.width, geom.height),
                                "window_class": wm_class,
                                "process_name": wm_class  # On Linux, use class as process indicator
                            })
                    
                    # Enumerate children
                    children = window.query_tree().children
                    for child in children:
                        enum_windows(child)
                        
                except Exception:
                    pass
            
            enum_windows(root)
            d.close()
            
        except Exception as e:
            logger.error(f"Error listing Linux windows: {e}")
        
        return windows
    
    @staticmethod
    def _list_windows_macos() -> List[Dict[str, Any]]:
        """List windows on macOS using Quartz."""
        windows = []
        
        try:
            import Quartz
            
            # Get window list
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            
            for window in window_list:
                # Get window properties
                window_id = window.get(Quartz.kCGWindowNumber, 0)
                title = window.get(Quartz.kCGWindowName, "Unnamed")
                owner = window.get(Quartz.kCGWindowOwnerName, "Unknown")
                bounds = window.get(Quartz.kCGWindowBounds, {})
                
                width = int(bounds.get('Width', 0))
                height = int(bounds.get('Height', 0))
                
                # Skip small windows
                if width > 50 and height > 50:
                    windows.append({
                        "handle": window_id,
                        "title": title or f"{owner} Window",
                        "resolution": (width, height),
                        "window_class": owner,
                        "process_name": owner
                    })
            
        except Exception as e:
            logger.error(f"Error listing macOS windows: {e}")
        
        return windows