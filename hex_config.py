import os
import pygame
from typing import List, Dict, Any

# ==========================================
# MODULE 1: CONFIGURATION & ASSETS
# ==========================================

class Config:
    """
    Central configuration management for the application.
    
    This class holds global constants, runtime settings, and utility methods
    for environment setup (directories, paths).
    """
    # Display settings
    WIDTH: int = 1280
    HEIGHT: int = 720
    FPS: int = 60
    
    # Directory settings
    # Using getcwd() allows the application to create the vault in the current execution context.
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    VAULT_DIR: str = os.path.join(BASE_DIR, "HEX_VAULT")
    
    # Security settings
    # Try to get the password from the OS (environment variable). 
    # If it's not set, fallback to "1234" for the demo.
    ACCESS_PASSWORD: str = os.getenv("HEX_ADMIN_PIN", "1234")
    
    # Visual Themes
    # Each palette defines the color scheme for the UI components.
    PALETTES: List[Dict[str, Any]] = [
        {"name": "CYAN", "bg": (10, 12, 16), "fill": (15, 20, 25), "accent": (0, 255, 255), "dim": (0, 100, 100), "text": (220, 225, 235), "dots": (20, 40, 50)},
        {"name": "ORANGE", "bg": (20, 10, 5), "fill": (30, 15, 10), "accent": (255, 140, 0), "dim": (120, 60, 0), "text": (255, 240, 220), "dots": (60, 30, 10)},
        {"name": "GREEN", "bg": (5, 10, 5), "fill": (0, 20, 0), "accent": (50, 255, 50), "dim": (0, 100, 0), "text": (200, 255, 200), "dots": (10, 50, 10)}
    ]

    @staticmethod
    def get_initial_path() -> str:
        """
        Determine a valid initial directory for the file picker.

        This method attempts to locate standard user directories (Desktop, Documents)
        to provide a convenient starting point. It validates existence and read permissions.

        Returns:
            str: The absolute path to a valid directory. Defaults to BASE_DIR if no
                 standard user directories are accessible.
        """
        home = os.path.expanduser("~")
        
        # Priority list for initial directory
        candidates = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "OneDrive", "Desktop"), # Handle OneDrive redirection on Windows
            os.path.join(home, "Documents"),
            home
        ]
        
        for path in candidates:
            # Check if path exists and is readable
            if os.path.exists(path) and os.access(path, os.R_OK):
                return path
                
        return Config.BASE_DIR

    @staticmethod
    def ensure_vault() -> None:
        """
        Ensure the vault directory exists on the filesystem.

        This acts as a safeguard to prevent IOErrors when the UI attempts to
        access the vault before any encryption operations have occurred.
        """
        try:
            os.makedirs(Config.VAULT_DIR, exist_ok=True)
        except OSError as e:
            # In production, this should log to a file. 
            # For now, we print to stderr to alert the developer/user.
            print(f"[CRITICAL] Failed to create vault directory at {Config.VAULT_DIR}: {e}")

class Assets:
    """
    Asset management for the application.
    
    Handles loading and caching of resources such as fonts.
    """
    FONTS: Dict[str, pygame.font.Font] = {}

    @staticmethod
    def load_fonts() -> None:
        """
        Initialize and load application fonts.

        This method iterates through a list of preferred monospace fonts to ensure
        consistent UI rendering across different operating systems (Windows, Linux, macOS).
        It populates the Assets.FONTS dictionary with pygame.font.SysFont objects.
        """
        # List of preferred fonts in descending order of preference.
        # We prioritize fonts that look "techy" or "terminal-like".
        valid_fonts = [
            "Consolas",          # Windows default monospace
            "Courier New",       # Universal fallback
            "Liberation Mono",   # Linux common
            "DejaVu Sans Mono",  # Linux common
            "monospace"          # Generic system alias
        ]
        
        selected_font_name = "monospace" # Default fallback
        
        # Check which font is actually available on the system
        for name in valid_fonts:
            if pygame.font.match_font(name):
                selected_font_name = name
                break

        # Initialize font objects with specific sizes and styles
        # SysFont is used here to load from system installed fonts by name.
        Assets.FONTS["MAIN"] = pygame.font.SysFont(selected_font_name, 20, bold=True)
        Assets.FONTS["SUB"] = pygame.font.SysFont(selected_font_name, 16)
        Assets.FONTS["TINY"] = pygame.font.SysFont(selected_font_name, 12)
        Assets.FONTS["BIG"] = pygame.font.SysFont(selected_font_name, 32, bold=True)
        Assets.FONTS["CORE"] = pygame.font.SysFont(selected_font_name, 26, bold=True)
        Assets.FONTS["CLOCK"] = pygame.font.SysFont(selected_font_name, 14, bold=True)