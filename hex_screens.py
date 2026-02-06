import pygame
import os
import random
import time
from typing import List, Optional, Any, Tuple
from hex_config import Config, Assets
from hex_gfx import Graphics

# ==========================================
# MODULE 5: ROBUST FILE PICKER
# ==========================================

class CustomFilePicker:
    """
    A robust, scrollable file selection widget.

    Handles directory navigation, file selection, and batch operation modes.
    Optimized for performance with large directories using view culling and scandir.
    """

    def __init__(self) -> None:
        """Initialize the file picker state and UI resources."""
        self.active: bool = False
        self.path: str = Config.get_initial_path()
        self.root_lock: Optional[str] = None
        self.batch_mode: bool = False
        self.files: List[str] = []
        
        # Scrolling physics
        self.scroll_y: float = 0.0
        self.tgt_scroll: float = 0.0
        
        self.sel_idx: int = -1
        self.last_click: int = 0
        self.selection_result: Optional[str] = None
        self.prompt_text: str = "SELECT FILE"
        
        # Pre-render the modal overlay
        self.overlay: pygame.Surface = pygame.Surface((Config.WIDTH, Config.HEIGHT))
        self.overlay.set_alpha(220)
        self.overlay.fill((5, 5, 8))
        
        # Layout placeholders
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.btn_up: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.btn_cancel: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.btn_act: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        
        self.recalc_layout()

    def recalc_layout(self) -> None:
        """Calculate UI element positions based on screen center."""
        cx, cy = Config.WIDTH // 2, Config.HEIGHT // 2
        self.rect = pygame.Rect(cx - 320, cy - 220, 640, 440)
        self.btn_up = pygame.Rect(self.rect.left + 20, self.rect.top + 20, 90, 30)
        self.btn_cancel = pygame.Rect(self.rect.left + 20, self.rect.bottom - 60, 100, 40)
        self.btn_act = pygame.Rect(self.rect.right - 220, self.rect.bottom - 60, 200, 40)

    def open(self, start_path: str, prompt: str, lock_to_root: bool = False, batch_mode: bool = False) -> None:
        """
        Activate the file picker.

        Args:
            start_path (str): The directory to start in.
            prompt (str): The title text to display.
            lock_to_root (bool): If True, prevents navigating up from start_path.
            batch_mode (bool): If True, allows selecting the current directory itself.
        """
        self.active = True
        self.path = start_path
        self.root_lock = start_path if lock_to_root else None
        self.batch_mode = batch_mode
        
        if not os.path.exists(self.path):
            self.path = Config.get_initial_path()
            
        self.prompt_text = prompt
        self.selection_result = None
        self.refresh()

    def refresh(self) -> None:
        """
        Populate the file list from the current directory.
        
        Uses os.scandir for better performance with large directories compared to os.listdir.
        """
        self.files = []
        try:
            # Verify read permissions before attempting to list
            if not os.access(self.path, os.R_OK):
                self.files = ["<PERMISSION DENIED>"]
                return

            # os.scandir is more efficient as it retrieves file attribute info 
            # (like is_dir) in the directory listing system call on many platforms.
            with os.scandir(self.path) as entries:
                # Separate directories and files for sorting
                dirs = []
                files = []
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                    if entry.is_dir():
                        dirs.append(entry.name)
                    else:
                        files.append(entry.name)
                
                # Sort alphabetically, case-insensitive
                dirs.sort(key=str.lower)
                files.sort(key=str.lower)
                
                self.files = dirs + files
                
        except OSError:
            self.files = ["<ERROR READING DIRECTORY>"]
            
        self.sel_idx = 0 if self.files else -1
        self.tgt_scroll = 0
        self.scroll_y = 0

    def update(self) -> None:
        """Update scrolling physics."""
        self.scroll_y += (self.tgt_scroll - self.scroll_y) * 0.2

    def ensure_visible(self) -> None:
        """Adjust scroll target to ensure the selected item is visible."""
        if self.sel_idx == -1:
            return
        
        # List area height is 280px, Item height is 35px
        view_h = 280
        item_h = 35
        
        item_top = self.sel_idx * item_h
        item_bottom = item_top + item_h
        
        # Viewport in content coordinates
        vp_top = -self.tgt_scroll
        vp_bottom = vp_top + view_h
        
        if item_top < vp_top:
            self.tgt_scroll = -item_top
        elif item_bottom > vp_bottom:
            self.tgt_scroll = -(item_bottom - view_h)

    def handle(self, e: pygame.event.Event, mgr: Any) -> None:
        """
        Handle input events.

        Args:
            e (pygame.event.Event): The input event.
            mgr (LayoutManager): Reference to the layout manager for logging.
        """
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.active = False
                mgr.log.add_log_direct("OPERATION CANCELLED")
            
            elif e.key == pygame.K_UP:
                if self.files:
                    self.sel_idx = max(0, self.sel_idx - 1)
                    self.ensure_visible()
            elif e.key == pygame.K_DOWN:
                if self.files:
                    self.sel_idx = min(len(self.files) - 1, self.sel_idx + 1)
                    self.ensure_visible()
            elif e.key == pygame.K_RETURN or e.key == pygame.K_RIGHT:
                if self.sel_idx != -1:
                    self.navigate_or_select(self.sel_idx)
                elif self.batch_mode and e.key == pygame.K_RETURN:
                    self.do_action()
            elif e.key == pygame.K_BACKSPACE or e.key == pygame.K_LEFT:
                if self.root_lock and os.path.abspath(self.path) == os.path.abspath(self.root_lock):
                    mgr.log.add_log_direct("ACCESS DENIED: VAULT ROOT LOCKED")
                else:
                    parent = os.path.dirname(self.path)
                    if os.path.exists(parent):
                        self.path = parent
                        self.refresh()

        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 4: # Scroll Up
                self.tgt_scroll = min(0, self.tgt_scroll + 40)
            elif e.button == 5: # Scroll Down
                max_s = -max(0, len(self.files) * 35 - 280)
                self.tgt_scroll = max(max_s, self.tgt_scroll - 40)
            elif e.button == 1:
                mx, my = e.pos
                
                if self.btn_up.collidepoint(mx, my):
                    if self.root_lock and os.path.abspath(self.path) == os.path.abspath(self.root_lock):
                        mgr.log.add_log_direct("ACCESS DENIED: VAULT ROOT LOCKED")
                        return 
                    
                    parent = os.path.dirname(self.path)
                    if os.path.exists(parent):
                        self.path = parent
                        self.refresh()
                    
                elif self.btn_cancel.collidepoint(mx, my):
                    self.active = False
                    mgr.log.add_log_direct("OPERATION CANCELLED")

                elif self.btn_act.collidepoint(mx, my):
                    self.do_action()
                
                if not self.batch_mode:
                    list_r = pygame.Rect(self.rect.x + 20, self.rect.y + 60, self.rect.w - 40, 280)
                    if list_r.collidepoint(mx, my):
                        idx = int((my - list_r.y - self.scroll_y) // 35)
                        if 0 <= idx < len(self.files):
                            now = pygame.time.get_ticks()
                            # Double click detection
                            if idx == self.sel_idx and now - self.last_click < 500:
                                self.navigate_or_select(idx)
                                return
                            self.last_click = now
                            self.sel_idx = idx

    def navigate_or_select(self, idx: int) -> None:
        """
        Enter a directory or select a file.

        Args:
            idx (int): The index of the file in self.files.
        """
        if idx < 0 or idx >= len(self.files):
            return 
        
        f_name = self.files[idx]
        if f_name.startswith("<"):
            return # Ignore error placeholders

        next_p = os.path.join(self.path, f_name)
        
        if os.path.isdir(next_p):
            if os.access(next_p, os.R_OK):
                self.path = next_p
                self.refresh()
        else:
            self.selection_result = next_p
            self.active = False

    def do_action(self) -> None:
        """Confirm the current selection."""
        if self.batch_mode:
            self.selection_result = self.path
            self.active = False
        else:
            if self.sel_idx != -1:
                self.navigate_or_select(self.sel_idx)

    def draw(self, surf: pygame.Surface, p: Any) -> None:
        """
        Render the file picker UI.

        Args:
            surf (pygame.Surface): Target surface.
            p (Dict): Color palette.
        """
        surf.blit(self.overlay, (0, 0))
        Graphics.draw_chamfered_rect(surf, self.rect, p['fill'], 0)
        Graphics.draw_chamfered_rect(surf, self.rect, p['accent'], 2)
        
        t = Assets.FONTS["CORE"].render(self.prompt_text, True, p['accent'])
        surf.blit(t, (self.rect.x + 120, self.rect.y + 20)) 
        
        is_locked = self.root_lock and os.path.abspath(self.path) == os.path.abspath(self.root_lock)
        btn_col = (50, 20, 20) if is_locked else p['dim']
        border_col = (200, 50, 50) if is_locked else p['dim']
        
        Graphics.draw_chamfered_rect(surf, self.btn_up, btn_col, 0)
        Graphics.draw_chamfered_rect(surf, self.btn_up, border_col, 1)
        up_txt = Assets.FONTS["SUB"].render("LOCKED" if is_locked else "UP", True, (255, 200, 200) if is_locked else p['accent'])
        surf.blit(up_txt, up_txt.get_rect(center=self.btn_up.center))

        lr = pygame.Rect(self.rect.x + 20, self.rect.y + 60, self.rect.w - 40, 280)
        pygame.draw.rect(surf, (10, 10, 12), lr)
        pygame.draw.rect(surf, p['dim'], lr, 1)
        surf.set_clip(lr)
        
        sy = lr.y + self.scroll_y
        
        # Optimization: View Culling
        # Only iterate over items that are actually visible in the viewport
        start_index = max(0, int((-self.scroll_y) // 35))
        end_index = min(len(self.files), start_index + (280 // 35) + 2)

        for i in range(start_index, end_index):
            f = self.files[i]
            fy = sy + i * 35
            
            sel = (i == self.sel_idx)
            # Note: os.path.isdir is called here for rendering icons. 
            # Since we cull the view, this only happens ~10 times per frame, which is acceptable.
            is_dir = os.path.isdir(os.path.join(self.path, f)) if not f.startswith("<") else False
            
            if sel:
                pygame.draw.rect(surf, p['dim'], (lr.x, fy, lr.w, 30))
            
            if f.startswith("<"):
                icon = "!"
                icol = (200, 50, 50)
            else:
                icon = "[DIR]" if is_dir else "[FILE]"
                icol = p['accent'] if is_dir else (150, 150, 150)
                
            surf.blit(Assets.FONTS["SUB"].render(icon, True, icol), (lr.x + 10, fy + 8))
            
            # Truncate long filenames for display
            display_name = f if len(f) < 45 else f[:42] + "..."
            surf.blit(Assets.FONTS["SUB"].render(display_name, True, p['accent'] if sel else p['text']), (lr.x + 80, fy + 8))
            
        surf.set_clip(None)

        Graphics.draw_chamfered_rect(surf, self.btn_cancel, (50, 20, 20), 0)
        Graphics.draw_chamfered_rect(surf, self.btn_cancel, (200, 50, 50), 1)
        c_t = Assets.FONTS["SUB"].render("CANCEL", True, (255, 200, 200))
        surf.blit(c_t, c_t.get_rect(center=self.btn_cancel.center))

        act_txt = "EXECUTE BATCH" if self.batch_mode else "CONFIRM"
        act_col = p['accent'] if self.batch_mode else p['dim']
        if not self.batch_mode and self.sel_idx != -1:
            if 0 <= self.sel_idx < len(self.files):
                fname = self.files[self.sel_idx]
                if not fname.startswith("<"):
                    act_txt = "OPEN FOLDER" if os.path.isdir(os.path.join(self.path, fname)) else "SELECT FILE"
                    act_col = p['accent']
        
        Graphics.draw_chamfered_rect(surf, self.btn_act, p['fill'], 0)
        Graphics.draw_chamfered_rect(surf, self.btn_act, act_col, 2)
        a_t = Assets.FONTS["MAIN"].render(act_txt, True, act_col)
        surf.blit(a_t, a_t.get_rect(center=self.btn_act.center))

# ==========================================
# MODULE 6: LOGIN SCREEN
# ==========================================
class LoginScreen:
    """
    The initial authentication screen.
    
    Handles PIN entry, validation, and visual feedback (shake animation on error).
    """

    def __init__(self) -> None:
        """Initialize login state."""
        self.input_text: str = ""
        self.shake: int = 0
        self.hex_rot: float = 0.0
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.recalc_layout()
    
    def recalc_layout(self) -> None:
        """Center the login box."""
        self.rect = pygame.Rect(Config.WIDTH // 2 - 150, Config.HEIGHT // 2 - 25, 300, 50)

    def handle(self, event: pygame.event.Event, app: Any) -> None:
        """
        Handle keyboard input for PIN entry.

        Args:
            event (pygame.event.Event): Input event.
            app (App): Reference to main application for state transition.
        """
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif len(self.input_text) < 4:
                if event.unicode.isdigit():
                    self.input_text += event.unicode
                    if len(self.input_text) == 4:
                        if self.input_text == Config.ACCESS_PASSWORD:
                            app.state = "MAIN"
                        else:
                            # Trigger error feedback
                            self.shake = 20
                            self.input_text = ""

    def update(self) -> None:
        """Update animations."""
        self.hex_rot += 1
        if self.shake > 0:
            self.shake -= 1

    def draw(self, surf: pygame.Surface, p: Any) -> None:
        """
        Render the login screen.

        Args:
            surf (pygame.Surface): Target surface.
            p (Dict): Color palette.
        """
        cx, cy = Config.WIDTH // 2, Config.HEIGHT // 2
        Graphics.draw_hex_ring(surf, cx, cy, 100, p['dim'], self.hex_rot, 2)
        t = Assets.FONTS["BIG"].render("SECURE ACCESS REQUIRED", True, p['accent'])
        surf.blit(t, t.get_rect(center=(cx, cy - 100)))
        
        shake_off = random.randint(-5, 5) if self.shake > 0 else 0
        box_r = self.rect.move(shake_off, 0)
        col = (255, 50, 50) if self.shake > 0 else p['accent']
        
        Graphics.draw_chamfered_rect(surf, box_r, p['fill'], 0)
        Graphics.draw_chamfered_rect(surf, box_r, col, 2)
        
        disp_txt = ""
        for i in range(4):
            if i < len(self.input_text): 
                disp_txt += "* "
            elif i == len(self.input_text) and time.time() % 1 > 0.5: 
                disp_txt += "_ "
            else: 
                disp_txt += ". "
        
        txt_s = Assets.FONTS["BIG"].render(disp_txt.strip(), True, p['text'])
        surf.blit(txt_s, txt_s.get_rect(center=box_r.center))
        
        h = Assets.FONTS["TINY"].render("ENTER 4-DIGIT PIN", True, p['dim'])
        surf.blit(h, h.get_rect(center=(cx, cy + 50)))