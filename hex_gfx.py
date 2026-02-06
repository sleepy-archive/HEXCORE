import pygame
import math
from typing import List, Tuple, Union, Optional
from hex_config import Config

class Graphics:
    """
    Static utility class for rendering custom UI elements and handling graphical operations.
    
    This class provides methods for drawing geometric shapes (chamfered rectangles, hexagons),
    generating background grids, and handling text layout (wrapping). It utilizes caching
    to optimize rendering performance for static elements like the background grid.
    """
    
    # Cache for the background dot grid to prevent expensive redraws every frame.
    # Stores a tuple of (Surface, Color) to ensure the cache is invalidated if the requested color changes.
    _grid_cache: Optional[Tuple[pygame.Surface, Tuple[int, int, int]]] = None

    @staticmethod
    def get_dot_grid(color: Tuple[int, int, int]) -> pygame.Surface:
        """
        Retrieve or generate the background dot grid surface.

        This method employs a caching strategy. If a grid with the specified color
        has already been generated, it returns the cached Surface. Otherwise, it
        creates a new Surface, draws the grid, and updates the cache.

        Args:
            color (Tuple[int, int, int]): The RGB color for the grid dots.

        Returns:
            pygame.Surface: A surface containing the rendered dot grid.
        """
        # Check if we have a valid cache and if the requested color matches the cached one.
        if Graphics._grid_cache is not None:
            cached_surface, cached_color = Graphics._grid_cache
            if cached_color == color:
                return cached_surface

        # Initialize a new surface with transparency support.
        # We use Config.WIDTH and Config.HEIGHT to ensure it covers the screen.
        surface = pygame.Surface((Config.WIDTH, Config.HEIGHT))
        
        # Set the colorkey to black (0,0,0) to make the background transparent,
        # assuming the dots are drawn on top of this "transparent" black.
        surface.set_colorkey((0, 0, 0))
        surface.fill((0, 0, 0))

        # Draw dots in a grid pattern.
        # Step size of 30 pixels creates the spacing between dots.
        for x in range(0, Config.WIDTH, 30):
            for y in range(0, Config.HEIGHT, 30):
                pygame.draw.circle(surface, color, (x, y), 1)

        # Update the cache with the new surface and the color used to generate it.
        Graphics._grid_cache = (surface, color)
        return surface

    @staticmethod
    def clear_cache() -> None:
        """
        Invalidate the graphics cache.

        This should be called when global display settings change (e.g., resolution)
        to force regeneration of cached assets.
        """
        Graphics._grid_cache = None

    @staticmethod
    def draw_chamfered_rect(
        surf: pygame.Surface, 
        rect: Union[pygame.Rect, Tuple[int, int, int, int]], 
        color: Tuple[int, int, int], 
        width: int = 0, 
        cut: int = 10
    ) -> None:
        """
        Draw a rectangle with chamfered (cut) corners.

        This creates a "sci-fi" or "tech" aesthetic compared to standard rounded rectangles.
        It also renders a subtle drop shadow if the shape is filled (width=0).

        Args:
            surf (pygame.Surface): The target surface to draw on.
            rect (Union[pygame.Rect, Tuple]): The bounding rectangle (x, y, w, h).
            color (Tuple[int, int, int]): The RGB color of the shape.
            width (int, optional): Line width. 0 fills the shape. Defaults to 0.
            cut (int, optional): The size of the corner cut in pixels. Defaults to 10.
        """
        # Unpack rectangle coordinates. Works for both tuples and pygame.Rect objects.
        if isinstance(rect, pygame.Rect):
            x, y, w, h = rect.x, rect.y, rect.width, rect.height
        else:
            x, y, w, h = rect

        # Define the 8 points that form the chamfered polygon.
        # We start from top-left (offset by cut) and move clockwise.
        points = [
            (x + cut, y),       # Top-Left (start of top edge)
            (x + w - cut, y),   # Top-Right (end of top edge)
            (x + w, y + cut),   # Top-Right (start of right edge)
            (x + w, y + h - cut), # Bottom-Right (end of right edge)
            (x + w - cut, y + h), # Bottom-Right (start of bottom edge)
            (x + cut, y + h),   # Bottom-Left (end of bottom edge)
            (x, y + h - cut),   # Bottom-Left (start of left edge)
            (x, y + cut)        # Top-Left (end of left edge)
        ]

        # If drawing a filled shape (width=0), draw a shadow first for depth.
        if width == 0:
            # Offset shadow points by 4 pixels down and right.
            shadow_points = [(p[0] + 4, p[1] + 4) for p in points]
            # Draw shadow with a dark color (almost black).
            pygame.draw.polygon(surf, (5, 5, 5), shadow_points)

        # Draw the main polygon.
        pygame.draw.polygon(surf, color, points, width)

    @staticmethod
    def draw_hex_ring(
        surf: pygame.Surface, 
        x: float, 
        y: float, 
        radius: float, 
        color: Tuple[int, int, int], 
        rotation: float, 
        width: int = 2
    ) -> None:
        """
        Draw a hexagon outline centered at (x, y).

        Args:
            surf (pygame.Surface): The target surface.
            x (float): Center X coordinate.
            y (float): Center Y coordinate.
            radius (float): Distance from center to vertex.
            color (Tuple[int, int, int]): RGB color.
            rotation (float): Rotation angle in degrees.
            width (int, optional): Line thickness. Defaults to 2.
        """
        points = []
        # A hexagon has 6 vertices. We calculate each using polar coordinates.
        for i in range(6):
            # Calculate angle: 60 degrees per segment + global rotation.
            # Convert to radians for math functions.
            ang_deg = 60 * i + rotation
            ang_rad = math.radians(ang_deg)
            
            # Convert polar (radius, angle) to cartesian (x, y).
            px = x + radius * math.cos(ang_rad)
            py = y + radius * math.sin(ang_rad)
            points.append((px, py))

        # Draw the closed polygon connecting the 6 points.
        pygame.draw.polygon(surf, color, points, width)

    @staticmethod
    def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """
        Wrap text to fit within a specified width.

        Handles standard space-based word wrapping. Includes a special heuristic
        for file paths (containing '/' or '\') to force character-based chunking,
        preventing long paths from overflowing the UI.

        Args:
            text (str): The input string.
            font (pygame.font.Font): The font used for size calculations.
            max_width (int): The maximum width in pixels allowed per line.

        Returns:
            List[str]: A list of strings, where each string is a line.
        """
        if not text:
            return []

        # Special handling for file paths:
        # Paths often lack spaces, breaking standard word wrapping.
        # If path separators are detected, we force a hard split every 35 characters.
        if "/" in text or "\\" in text: 
            chunk_size = 35
            return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            # Test if adding the next word exceeds the max width.
            # We join with a space to simulate the actual rendered line.
            test_line_words = current_line + [word]
            test_line_str = ' '.join(test_line_words)
            
            # font.size returns (width, height). We only care about width [0].
            if font.size(test_line_str)[0] < max_width:
                current_line.append(word)
            else:
                # If the line is too long, push the current line to results
                # and start a new line with the current word.
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Edge case: The word itself is wider than max_width.
                    # We must force it onto the line to avoid infinite loops or dropping words.
                    lines.append(word)
                    current_line = []

        # Append any remaining text in the buffer.
        if current_line:
            lines.append(' '.join(current_line))
            
        return lines