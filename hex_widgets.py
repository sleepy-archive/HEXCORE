import pygame
import math
import random
import time
import datetime
from typing import Dict, List, Tuple, Optional, Any

from hex_config import Config, Assets
from hex_gfx import Graphics

class FloatingHex:
    """
    Represents a decorative hexagon floating in the background.
    
    This widget manages its own position, rotation, and lifecycle (resetting
    when it moves off-screen).
    """

    def __init__(self, palette: Dict[str, Any]) -> None:
        """
        Initialize the floating hexagon.

        Args:
            palette (Dict[str, Any]): The color palette configuration.
        """
        self.x: float = 0
        self.y: float = 0
        self.size: int = 0
        self.speed: float = 0.0
        self.color: Tuple[int, int, int] = (0, 0, 0)
        self.rotation: float = 0.0
        
        self.reset(palette)
        # Randomize start Y to distribute hexes across the screen initially
        self.y = random.randint(0, Config.HEIGHT)

    def reset(self, palette: Dict[str, Any]) -> None:
        """
        Reset the hexagon's properties for a new lifecycle.

        Args:
            palette (Dict[str, Any]): The color palette to derive colors from.
        """
        self.size = random.randint(20, 50)
        self.x = random.randint(0, Config.WIDTH)
        # Start below the screen to float up
        self.y = Config.HEIGHT + 50
        self.speed = random.uniform(0.5, 1.5)
        
        # Randomly choose between the palette's dim color or a fixed dark slate
        # to add visual variety.
        dim_col = palette.get('dim', (30, 40, 50))
        self.color = random.choice([dim_col, (30, 40, 50)])
        self.rotation = random.uniform(0, 360)

    def update(self) -> None:
        """
        Update position and rotation. Resets if the hex moves off-screen.
        """
        self.y -= self.speed
        self.rotation += 0.2
        
        # Boundary check: If it floats off the top, reset it to the bottom.
        if self.y < -50: 
            # Pass current color as 'dim' to maintain consistency if needed,
            # or just to satisfy the signature.
            self.reset({"dim": self.color})
            self.y = Config.HEIGHT + 50

    def draw(self, surf: pygame.Surface) -> None:
        """
        Render the hexagon to the target surface.

        Args:
            surf (pygame.Surface): The surface to draw on.
        """
        Graphics.draw_hex_ring(
            surf, self.x, self.y, self.size, self.color, self.rotation, 1
        )


class HexCoreLog:
    """
    A scrollable log widget displaying system events and important messages.
    
    Features:
    - Important message banner (top).
    - Scrollable history (bottom).
    - Automatic text wrapping.
    - Performance optimizations (surface caching, view culling).
    """

    def __init__(self) -> None:
        """Initialize the log widget."""
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.imp_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.std_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        
        # Cache the background surface to avoid per-frame allocation
        self._cached_glass: Optional[pygame.Surface] = None
        
        self.imp_msg: str = "SYSTEM READY"
        self.std_logs: List[str] = []
        
        # Scrolling state
        self.scroll_std: float = 0.0
        self.tgt_std: float = 0.0
        self.line_height: int = 14
        
        self.recalc_layout()
        
        self.add_log_direct("KERNEL_INIT_OK")
        self.add_log_direct("HEXCORE DAEMON STARTED")

    def recalc_layout(self) -> None:
        """
        Recalculate layout coordinates and regenerate cached surfaces.
        
        Should be called when screen resolution changes.
        """
        self.rect = pygame.Rect(Config.WIDTH - 320, 90, 300, 265)
        self.imp_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 10, self.rect.width - 20, 40)
        self.std_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 80, self.rect.width - 20, 150)
        
        # Create a semi-transparent background surface once
        self._cached_glass = pygame.Surface(self.rect.size, pygame.SRCALPHA)

    def set_important(self, text: str) -> None:
        """
        Set the high-priority message displayed at the top of the log.

        Args:
            text (str): The message to display.
        """
        self.imp_msg = text
        self.add_log_direct(f">> {text}")

    def add_log_direct(self, text: str) -> None:
        """
        Add a standard log entry with timestamp and wrapping.

        Args:
            text (str): The log message.
        """
        t_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Wrap text to fit the log width
        lines = Graphics.wrap_text(text, Assets.FONTS["TINY"], self.std_rect.width - 10)
        
        for i, line in enumerate(lines):
            prefix = f"[{t_str}] " if i == 0 else "          "
            self.std_logs.append(f"{prefix}{line}")
        
        # Prune old logs to prevent memory bloat
        if len(self.std_logs) > 500: 
            self.std_logs = self.std_logs[-500:]
            
        # Auto-scroll to bottom
        # We set target to a very low number; update() will clamp it to the valid range.
        self.tgt_std = -float('inf')

    def handle_input(self, event: pygame.event.Event) -> None:
        """
        Handle mouse interaction (scrolling).

        Args:
            event (pygame.event.Event): The input event.
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if self.std_rect.collidepoint(mx, my):
                visible_h = self.std_rect.height - 10
                total_h = len(self.std_logs) * self.line_height
                
                # Scroll speed constant
                scroll_step = 40
                
                if event.button == 4: # Scroll Up
                    self.tgt_std = min(0, self.tgt_std + scroll_step)
                elif event.button == 5 and total_h > visible_h: # Scroll Down
                    min_scroll = -(total_h - visible_h)
                    self.tgt_std = max(min_scroll, self.tgt_std - scroll_step)

    def update(self) -> None:
        """Update scrolling physics."""
        visible_h = self.std_rect.height - 10
        total_h = len(self.std_logs) * self.line_height
        
        if total_h < visible_h:
            self.tgt_std = 0
        else:
            min_scroll = -(total_h - visible_h)
            # Clamp target scroll to valid bounds
            if self.tgt_std < min_scroll: 
                self.tgt_std = min_scroll
            if self.tgt_std > 0: 
                self.tgt_std = 0
            
        # Smooth interpolation (Lerp)
        self.scroll_std += (self.tgt_std - self.scroll_std) * 0.2

    def draw(self, surf: pygame.Surface, palette: Dict[str, Any]) -> None:
        """
        Render the log widget.

        Args:
            surf (pygame.Surface): Target surface.
            palette (Dict[str, Any]): Color palette.
        """
        # 1. Draw Background
        # Re-fill cached surface to support palette changes without re-allocation
        if self._cached_glass is None:
             self._cached_glass = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        
        fill = palette['fill']
        self._cached_glass.fill((0, 0, 0, 0)) # Clear previous
        self._cached_glass.fill((fill[0], fill[1], fill[2], 90))
        surf.blit(self._cached_glass, self.rect.topleft)
        
        Graphics.draw_chamfered_rect(surf, self.rect, palette['accent'], 2)

        # 2. Draw Important Message Box
        Graphics.draw_chamfered_rect(surf, self.imp_rect, palette['fill'], 0)
        Graphics.draw_chamfered_rect(surf, self.imp_rect, palette['accent'], 1)
        
        t = Assets.FONTS["SUB"].render(self.imp_msg, True, palette['accent'])
        # Scale text if it overflows the box
        if t.get_width() > self.imp_rect.width - 20:
             t = pygame.transform.scale(t, (self.imp_rect.width - 20, t.get_height()))
        surf.blit(t, t.get_rect(center=self.imp_rect.center))

        # 3. Draw Header
        head = Assets.FONTS["TINY"].render("EVENT_LOG // HISTORY", True, palette['dim'])
        surf.blit(head, (self.std_rect.x, self.std_rect.y - 15))
        
        # 4. Draw Logs (Clipped)
        surf.set_clip(self.std_rect)
        
        start_y = self.std_rect.y + 5 + self.scroll_std
        
        # Optimization: Calculate visible index range to avoid iterating all logs
        # y = start_y + i * line_height
        # Visible if: y + line_height > rect.top AND y < rect.bottom
        
        # i * line_height > rect.top - start_y - line_height
        # i > (rect.top - start_y - line_height) / line_height
        first_idx = int((self.std_rect.y - start_y - self.line_height) / self.line_height)
        first_idx = max(0, first_idx)
        
        # i * line_height < rect.bottom - start_y
        last_idx = int((self.std_rect.bottom - start_y) / self.line_height)
        last_idx = min(len(self.std_logs), last_idx + 1)
        
        for i in range(first_idx, last_idx):
            log = self.std_logs[i]
            ly = start_y + (i * self.line_height)
            
            # Highlight recent logs
            alpha = 255 if i > len(self.std_logs) - 5 else 180
            
            t = Assets.FONTS["TINY"].render(log, True, palette['text'])
            t.set_alpha(alpha)
            surf.blit(t, (self.std_rect.x + 5, ly))
            
        surf.set_clip(None)

class CentralCore:
    """
    The central UI element displaying status, descriptions, and animations.
    
    Handles the "breathing" animation and text transitions.
    """

    def __init__(self) -> None:
        """Initialize the central core widget."""
        self.rot_a: float = 0.0
        self.rot_b: float = 0.0
        
        self.tgt_txt: str = "SYSTEM READY"
        self.tgt_desc: str = "WAITING FOR INPUT"
        self.disp_txt: str = self.tgt_txt
        self.disp_desc: str = self.tgt_desc
        
        # Animation states
        self.alpha: int = 255
        self.off_x: float = 0.0
        self.state: str = "IDLE" # IDLE, OUT, IN
        
        self.arrow_l: int = 0
        self.arrow_r: int = 0
        self.bob: float = 0.0
        
        # Mapping of action keywords to user-friendly descriptions
        self.desc_map: Dict[str, str] = {
            "AES-256": "MILITARY GRADE // STANDARD",
            "RSA-4096": "ASYMMETRIC // HIGH LATENCY",
            "CHACHA20": "STREAM CIPHER // FAST",
            "VERIFY": "INTEGRITY CHECK // CHECKSUM",
            "RESTORE": "DECRYPT // RECOVER",
            "THEME": "VISUAL CONFIG // TOGGLE",
            "EXIT": "TERMINATE SESSION",
            "BROWSING...": "SELECT FILE // AWAITING INPUT",
            "ACCESSING VAULT...": "SECURE STORAGE // LOCKED",
            "CHANGE PASSWORD": "UPDATE ACCESS CREDENTIALS",
            "LOCK SYSTEM": "SECURE LOGOUT // STANDBY"
        }

    def set_status(self, txt: str, custom_desc: Optional[str] = None) -> None:
        """
        Trigger a status change animation.

        Args:
            txt (str): The main status text.
            custom_desc (Optional[str]): Optional custom description. 
                                         If None, looks up in desc_map.
        """
        desc = custom_desc if custom_desc else self.desc_map.get(txt, "SELECTED // ACTIVE")
        
        # Only trigger animation if text changes
        if txt != self.tgt_txt or custom_desc:
            self.tgt_txt, self.tgt_desc = txt, desc
            self.state = "OUT"

    def update(self) -> None:
        """Update animations and transition state machine."""
        self.rot_a += 0.5
        self.rot_b -= 0.3
        self.bob += 0.1
        
        # Decay arrow highlights
        if self.arrow_l > 0: self.arrow_l -= 1
        if self.arrow_r > 0: self.arrow_r -= 1

        # Text Transition State Machine
        if self.state == "OUT":
            # Slide out to the left and fade
            self.off_x += (-100 - self.off_x) * 0.1
            self.alpha = max(0, self.alpha - 20)
            
            if self.alpha <= 0:
                # Swap text and reset position for entry
                self.disp_txt, self.disp_desc = self.tgt_txt, self.tgt_desc
                self.off_x = 100
                self.state = "IN"
                
        elif self.state == "IN":
            # Slide in from the right and fade in
            self.off_x += (0 - self.off_x) * 0.1
            self.alpha = min(255, self.alpha + 20)
            
            if self.alpha >= 255 and abs(self.off_x) < 1:
                self.state = "IDLE"

    def draw(self, surf: pygame.Surface, cx: int, cy: int, p: Dict[str, Any]) -> None:
        """
        Render the central core.

        Args:
            surf (pygame.Surface): Target surface.
            cx (int): Center X coordinate.
            cy (int): Center Y coordinate.
            p (Dict[str, Any]): Color palette.
        """
        # Draw rotating rings
        Graphics.draw_hex_ring(surf, cx, cy, 160, p['dim'], self.rot_a, 4)
        Graphics.draw_hex_ring(surf, cx, cy, 220, p['dim'], self.rot_b, 3)
        
        # Draw Side Arrows (Brackets)
        off = 260
        bob_offset = math.sin(self.bob) * 5
        bh = 60 # Bracket height
        
        # Left Bracket
        col_l = p['accent'] if self.arrow_l > 0 else p['dim']
        lx = cx - off + bob_offset
        pygame.draw.lines(surf, col_l, False, [(lx, cy-bh), (lx-30, cy), (lx, cy+bh)], 4)
        
        # Right Bracket
        col_r = p['accent'] if self.arrow_r > 0 else p['dim']
        rx = cx + off - bob_offset
        pygame.draw.lines(surf, col_r, False, [(rx, cy-bh), (rx+30, cy), (rx, cy+bh)], 4)

        # Draw Clock
        t_str = datetime.datetime.now().strftime("%H:%M:%S")
        clk = Assets.FONTS["CLOCK"].render(f"SYS_TIME // {t_str}", True, p['dim'])
        surf.blit(clk, clk.get_rect(center=(cx, cy-70)))

        # Draw Status Text
        if self.alpha > 5:
            t = Assets.FONTS["CORE"].render(self.disp_txt, True, p['text'])
            t.set_alpha(self.alpha)
            surf.blit(t, t.get_rect(center=(cx + self.off_x, cy - 10)))
            
            d = Assets.FONTS["SUB"].render(self.disp_desc, True, p['accent'])
            d.set_alpha(self.alpha)
            surf.blit(d, d.get_rect(center=(cx + self.off_x, cy + 30)))

class FloatyButton:
    """
    A UI button that floats/bobs gently.
    
    Optimized to cache text rendering to minimize CPU usage.
    """

    def __init__(self, x: int, y: int, w: int, h: int, text: str) -> None:
        """
        Initialize the button.

        Args:
            x, y, w, h (int): Dimensions and position.
            text (str): Button label.
        """
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.base_y: float = float(y)
        self.cur_y: float = float(y)
        self.offset = random.uniform(0, 10)
        
        # Cache for rendered text surfaces to avoid re-rendering every frame
        self._cached_text_surf: Optional[pygame.Surface] = None
        self._cached_text_sel_surf: Optional[pygame.Surface] = None
        self._last_palette_name: Optional[str] = None

    def update(self, selected: bool) -> None:
        """
        Update the vertical position (bobbing animation).

        Args:
            selected (bool): Whether the button is currently focused.
        """
        # Target Y changes if selected (moves up slightly)
        target = self.base_y + (-8 if selected else 0) + (math.sin(time.time()*2 + self.offset)*2)
        
        # Smooth interpolation
        self.cur_y += (target - self.cur_y) * 0.05
        self.rect.y = int(self.cur_y)

    def draw(self, surf: pygame.Surface, selected: bool, p: Dict[str, Any]) -> None:
        """
        Render the button.

        Args:
            surf (pygame.Surface): Target surface.
            selected (bool): Focus state.
            p (Dict[str, Any]): Color palette.
        """
        # Check if we need to regenerate cached text (e.g., if palette changed)
        # We assume palette name is unique or we just check text color match.
        # For simplicity, we'll check if cache exists. In a real app, we'd check palette version.
        # Here we just check if it's None or if we want to be robust against palette swaps.
        if self._cached_text_surf is None or self._last_palette_name != p.get('name', ''):
            self._last_palette_name = p.get('name', '')
            self._cached_text_surf = Assets.FONTS["MAIN"].render(self.text, True, (150, 150, 150))
            self._cached_text_sel_surf = Assets.FONTS["MAIN"].render(self.text, True, p['text'])

        draw_rect = self.rect.copy()
        
        col = p['accent'] if selected else p['dim']
        
        # Draw background and border
        Graphics.draw_chamfered_rect(surf, draw_rect, p['fill'], 0)
        Graphics.draw_chamfered_rect(surf, draw_rect, col, 3 if selected else 2)
        
        # Blit cached text
        txt_surf = self._cached_text_sel_surf if selected else self._cached_text_surf
        if txt_surf:
            surf.blit(txt_surf, txt_surf.get_rect(center=self.rect.center))