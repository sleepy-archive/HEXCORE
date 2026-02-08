import glob
import os
import queue
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import pygame

import hex_engine
import hex_file_mgmt
from hex_config import Assets, Config
from hex_gfx import Graphics
from hex_screens import CustomFilePicker, LoginScreen
from hex_widgets import CentralCore, FloatingHex, FloatyButton, HexCoreLog

class LayoutManager:
    """
    Manages the primary application layout, user interactions, and background task orchestration.
    
    This class acts as the central controller for the authenticated session, handling
    navigation between tabs, executing encryption/decryption tasks, and updating the UI state.
    It employs a producer-consumer pattern with a thread-safe queue to handle background
    operations without freezing the main UI thread.
    """

    def __init__(self) -> None:
        """
        Initialize the layout manager, backend engines, and UI components.
        
        Sets up the encryption engine, vault manager, and UI widgets.
        Initializes the thread-safe queue for background task communication.
        """
        self.focus_area: str = "TOP"
        self.focus_idx: int = 0
        self.mode: str = 'ENCRYPT'
        
        # Loading state management
        self.loading: bool = False
        self.load_prog: float = 0.0
        self.vis_load_prog: float = 0.0
        self.load_txt: str = ""
        
        # Backend Initialization
        self.engine = hex_engine.EncryptionManager()
        self.vault = hex_file_mgmt.VaultManager(vault_dir=Config.VAULT_DIR)
        
        self.pending_task: Optional[str] = None
        
        # Thread-safe queue for UI updates from background threads
        # Background threads push messages here; the main loop consumes them.
        self.ui_queue: queue.Queue = queue.Queue()
        
        # UI Components
        self.core = CentralCore()
        self.log = HexCoreLog()
        self.picker = CustomFilePicker()
        
        self.tabs: List[str] = ["ENCRYPT", "DECRYPT", "SYSTEM"]
        self.actions: Dict[str, List[str]] = {
            'ENCRYPT': ['AES-256', 'RSA-4096', 'CHACHA20'],
            'DECRYPT': ['RESTORE', 'VERIFY'],
            'SYSTEM':  ['CHANGE PASSWORD', 'LOCK SYSTEM', 'THEME', 'EXIT']
        }
        
        self.tab_btns: List[FloatyButton] = []
        self.act_btns: List[FloatyButton] = []
        
        # Cache for UI surfaces to improve rendering performance
        self._cached_palette_name: Optional[str] = None
        self._top_bar_surf: Optional[pygame.Surface] = None
        self._overlay_surf: Optional[pygame.Surface] = None

        self._refresh_dock()

    def _refresh_dock(self) -> None:
        """
        Recalculate and position the dock buttons based on the current mode.
        
        This method updates the list of active buttons for the top navigation
        tabs and the bottom action bar, centering them horizontally on the screen.
        It also ensures the focus index remains valid after the button list changes.
        """
        self.tab_btns.clear()
        tab_width, spacing = 200, 20
        
        # Center the tab buttons horizontally
        total_tab_w = len(self.tabs) * tab_width + (len(self.tabs) - 1) * spacing
        start_x_tabs = (Config.WIDTH - total_tab_w) // 2
        
        for i, tab_name in enumerate(self.tabs):
            x_pos = start_x_tabs + i * (tab_width + spacing)
            self.tab_btns.append(FloatyButton(x_pos, 15, tab_width, 40, tab_name))

        self.act_btns.clear()
        action_labels = self.actions.get(self.mode, [])
        btn_width = 250
        
        # Center the action buttons horizontally
        total_act_w = len(action_labels) * btn_width + (len(action_labels) - 1) * spacing
        start_x_acts = (Config.WIDTH - total_act_w) // 2
        
        for i, label in enumerate(action_labels):
            x_pos = start_x_acts + i * (btn_width + spacing)
            # Position at bottom of screen
            self.act_btns.append(FloatyButton(x_pos, Config.HEIGHT - 90, btn_width, 60, label))
        
        # Ensure focus index is valid if the number of buttons changed
        if self.focus_area == "BOTTOM": 
            self.focus_idx = min(self.focus_idx, max(0, len(self.act_btns) - 1))

    def _thread_task(self, action: str, target_path: str) -> None:
        """
        Execute long-running cryptographic tasks in a background thread.
        
        Args:
            action: The operation identifier (e.g., "AES-256", "RESTORE").
            target_path: The file system path to operate on.
            
        Note:
            Catches all exceptions to prevent thread crashes from bringing down the app.
            Puts results into self.ui_queue for the main thread to display.
        """
        try:
            self.ui_queue.put(("PROGRESS", 0.1))
            
            if action == "RESTORE":
                self._handle_restore()
            elif action == "VERIFY":
                self._handle_verify()
            elif action in ["AES-256", "CHACHA20"]:
                self._handle_encryption(action, target_path)
            
            self.ui_queue.put(("PROGRESS", 1.0))
            # Artificial delay to ensure the user perceives the completion state
            time.sleep(0.5) 
                
        except Exception as e:
            self.ui_queue.put(("IMPORTANT", f"CRITICAL ERROR: {str(e)[:20]}"))
            # Log full traceback to console for debugging purposes
            traceback.print_exc()
        finally:
            self.ui_queue.put(("FINISH", None))

    def _handle_restore(self) -> None:
        """
        Handle the vault restoration process.
        
        Decrypts all files in the vault and moves them to the export directory.
        """
        self.ui_queue.put(("LOG", "UNLOCKING VAULT..."))
        stats = self.vault.decrypt_vault(self.engine, Config.ACCESS_PASSWORD, delete_encrypted=True)
        
        if isinstance(stats, str):
            self.ui_queue.put(("IMPORTANT", stats))
        else:
            self.ui_queue.put(("LOG", f"SUCCESS: {stats['success']} | FAIL: {stats['failed']}"))
            for err in stats.get('errors', []):
                self.ui_queue.put(("LOG", f"ERR: {err}"))
            self.ui_queue.put(("IMPORTANT", "VAULT RESTORE COMPLETE"))

    def _handle_verify(self) -> None:
        """
        Handle the vault integrity verification process.
        
        Scans all .hxc files in the vault and verifies their checksums against
        the file body to detect corruption or tampering.
        """
        self.ui_queue.put(("LOG", "SCANNING VAULT INTEGRITY..."))
        vault_files = glob.glob(os.path.join(Config.VAULT_DIR, "*.hxc"))
        
        if not vault_files:
            self.ui_queue.put(("IMPORTANT", "VAULT IS EMPTY"))
            return

        total = len(vault_files)
        issues = 0
        for i, vf in enumerate(vault_files):
            self.ui_queue.put(("PROGRESS", (i + 1) / total))
            fname = os.path.basename(vf)
            status = self.engine.verify_integrity(vf)
            
            if status != "INTEGRITY OK":
                self.ui_queue.put(("LOG", f"FAIL: {fname} [{status}]"))
                issues += 1
            
            # Artificial delay for visual feedback on progress bar
            time.sleep(0.05)
        
        if issues == 0:
            self.ui_queue.put(("IMPORTANT", "ALL FILES VERIFIED OK"))
        else:
            self.ui_queue.put(("IMPORTANT", f"FOUND {issues} CORRUPTED FILES"))

    def _handle_encryption(self, action: str, target_path: str) -> None:
        """
        Handle file encryption.
        
        Args:
            action (str): The encryption algorithm to use ("CHACHA20" or "AES-256").
            target_path (str): The path to the file to encrypt.
        """
        self.ui_queue.put(("LOG", f"ENCRYPTING: {os.path.basename(target_path)}"))
        
        algo_id = hex_engine.HexHeader.ALGO_CHACHA if action == "CHACHA20" else hex_engine.HexHeader.ALGO_AES

        result = self.vault.encrypt_and_store(
            target_path, 
            self.engine, 
            Config.ACCESS_PASSWORD,
            algo_id=algo_id,
            delete_original=True
        )
        
        if "SUCCESS" in result:
            self.ui_queue.put(("IMPORTANT", "ENCRYPTION SUCCESSFUL"))
            self.ui_queue.put(("LOG", "FILE MOVED TO VAULT"))
        else:
            self.ui_queue.put(("IMPORTANT", f"FAILED: {result}"))

    def execute_task(self, action: str, filepath: str) -> None:
        """
        Initiate a background task for encryption or decryption.
        
        Args:
            action: The action to perform.
            filepath: The target file path.
            
        Note:
            Sets the loading state to True, which blocks user input until completion.
        """
        self.core.set_status(action)
        self.loading = True
        self.load_prog = 0.0
        self.vis_load_prog = 0.0
        self.load_txt = action
        self.log.add_log_direct(f"INITIATING: {action}")
        
        # Daemon thread ensures it doesn't block program exit
        t = threading.Thread(target=self._thread_task, args=(action, filepath))
        t.daemon = True
        t.start()

    def _process_queue(self) -> None:
        """
        Process pending UI updates from the background thread.
        
        This must be called on the main thread to safely update Pygame surfaces.
        """
        try:
            while True:
                kind, data = self.ui_queue.get_nowait()
                if kind == "LOG":
                    self.log.add_log_direct(data)
                elif kind == "IMPORTANT":
                    self.log.set_important(data)
                elif kind == "PROGRESS":
                    self.load_prog = data
                elif kind == "FINISH":
                    self.loading = False
        except queue.Empty:
            pass

    def trigger_action(self, text: str, app: 'App') -> None:
        """
        Handle action button triggers and dispatch logic.
        
        Args:
            text: The label of the triggered button.
            app: Reference to the main App instance (for state transitions).
        """
        if self.loading:
            return

        if text == "EXIT":
            pygame.quit()
            sys.exit()
        elif text == "THEME": 
            app.toggle_theme()
            self.log.add_log_direct("THEME SWAPPED")
        elif text == "LOCK SYSTEM":
            app.lock_system()
        elif text == "CHANGE PASSWORD":
            self.log.set_important("FEATURE UNDER MAINTENANCE")
        
        elif text in ['AES-256', 'CHACHA20']:
            self.pending_task = text
            self.core.set_status("BROWSING...")
            self.picker.open(Config.get_initial_path(), f"SELECT FILE FOR {text}", lock_to_root=False, batch_mode=False)
            
        elif text == 'RSA-4096':
            self.log.set_important("ALGORITHM NOT SUPPORTED")
            
        elif text in ['RESTORE', 'VERIFY']:
            self.pending_task = text
            self.core.set_status("ACCESSING VAULT...")
            self.picker.open(Config.VAULT_DIR, f"BATCH {text} (ALL FILES)", lock_to_root=True, batch_mode=True)

    def handle_input(self, event: pygame.event.Event, app: 'App') -> None:
        """
        Dispatch input events to the appropriate UI component based on focus.
        
        Args:
            event: The pygame event.
            app: Reference to the main App instance.
        """
        if self.picker.active:
            return self.picker.handle(event, self)
        
        if self.loading:
            return
        
        # Log interaction
        if event.type == pygame.MOUSEBUTTONDOWN and self.log.rect.collidepoint(event.pos):
            return self.log.handle_input(event)

        # Mouse hover effects
        if event.type == pygame.MOUSEMOTION:
            for i, b in enumerate(self.tab_btns):
                if b.rect.collidepoint(event.pos):
                    self.focus_area, self.focus_idx = "TOP", i
            for i, b in enumerate(self.act_btns):
                if b.rect.collidepoint(event.pos):
                    self.focus_area, self.focus_idx = "BOTTOM", i

        # Mouse clicks
        if event.type == pygame.MOUSEBUTTONDOWN:
            for i, b in enumerate(self.tab_btns):
                if b.rect.collidepoint(event.pos):
                    self.mode = self.tabs[i]
                    self._refresh_dock()
                    self.core.set_status(self.mode)
                    self.log.add_log_direct(f"MODE SWITCH: {self.mode}")
            for i, b in enumerate(self.act_btns):
                if b.rect.collidepoint(event.pos):
                    self.trigger_action(b.text, app)

        # Keyboard navigation
        if event.type == pygame.KEYDOWN:
            self._handle_keyboard(event, app)

    def _handle_keyboard(self, event: pygame.event.Event, app: 'App') -> None:
        """
        Handle keyboard navigation logic for the dock and tabs.
        
        Args:
            event: The keydown event.
            app: Reference to the main App instance.
        """
        if event.key == pygame.K_DOWN and self.focus_area == "TOP":
            self.focus_area = "BOTTOM"
            self.focus_idx = 0
            if self.act_btns: 
                self.core.set_status(self.act_btns[0].text)
        elif event.key == pygame.K_UP and self.focus_area == "BOTTOM":
            self.focus_area = "TOP"
            for i, t in enumerate(self.tabs):
                if t == self.mode:
                    self.focus_idx = i
            self.core.set_status(self.mode)
        
        btns = self.tab_btns if self.focus_area == "TOP" else self.act_btns
        if btns:
            if event.key == pygame.K_RIGHT:
                self.focus_idx = (self.focus_idx + 1) % len(btns)
                self.core.arrow_r = 10
            elif event.key == pygame.K_LEFT:
                self.focus_idx = (self.focus_idx - 1) % len(btns)
                self.core.arrow_l = 10
            
            if self.focus_area == "TOP":
                self.mode = self.tabs[self.focus_idx]
                self._refresh_dock()
                self.core.set_status(self.mode)
            else:
                self.core.set_status(self.act_btns[self.focus_idx].text)

        if event.key == pygame.K_RETURN and self.focus_area == "BOTTOM":
            self.trigger_action(self.act_btns[self.focus_idx].text, app)

    def update(self) -> None:
        """
        Update the state of all active UI components.
        
        Checks the UI queue, updates animations, and handles file picker results.
        """
        self._process_queue() 
        
        if self.loading:
            # Smoothly interpolate visual progress towards actual progress (0.2 = fast but smooth)
            self.vis_load_prog += (self.load_prog - self.vis_load_prog) * 0.2

        if self.picker.active:
            return self.picker.update()
        
        if self.picker.selection_result and self.pending_task:
            filepath = self.picker.selection_result
            action = self.pending_task
            self.picker.selection_result = None
            self.pending_task = None
            
            if os.path.exists(filepath):
                self.log.add_log_direct("TARGET ACQUIRED")
                self.execute_task(action, filepath)
            else:
                self.log.set_important("ERROR: FILE MISSING")
            
        self.log.update()
        self.core.update()
        
        for i, b in enumerate(self.tab_btns):
            b.update(self.focus_area == "TOP" and self.focus_idx == i)
        
        if not self.loading:
            for i, b in enumerate(self.act_btns):
                b.update(self.focus_area == "BOTTOM" and self.focus_idx == i)

    def draw(self, surf: pygame.Surface, p: Dict[str, Any]) -> None:
        """
        Render the entire layout to the screen.
        
        Args:
            surf: The target pygame surface.
            p: The current color palette configuration.
        """
        # Invalidate cache if palette changes
        if self._cached_palette_name != p['name']:
            self._cached_palette_name = p['name']
            self._top_bar_surf = None
            self._overlay_surf = None

        self.core.draw(surf, Config.WIDTH//2, Config.HEIGHT//2, p)
        
        # Draw Top Bar (Cached)
        if self._top_bar_surf is None:
            self._top_bar_surf = pygame.Surface((Config.WIDTH, 70))
            self._top_bar_surf.set_alpha(200)
            self._top_bar_surf.fill(p['fill'])
        
        surf.blit(self._top_bar_surf, (0, 0))
        pygame.draw.line(surf, p['dim'], (0, 70), (Config.WIDTH, 70), 2)
        
        for i, b in enumerate(self.tab_btns):
            b.draw(surf, (self.focus_area == "TOP" and self.focus_idx == i), p)
        
        if not self.loading:
            for i, b in enumerate(self.act_btns):
                b.draw(surf, (self.focus_area == "BOTTOM" and self.focus_idx == i), p)
        else:
            self._draw_loading_overlay(surf, p)

        self.log.draw(surf, p)
        if self.picker.active:
            self.picker.draw(surf, p)

    def _draw_loading_overlay(self, surf: pygame.Surface, p: Dict[str, Any]) -> None:
        """
        Draw the modal loading overlay.
        
        Args:
            surf: Target surface.
            p: Color palette.
        """
        if self._overlay_surf is None:
            self._overlay_surf = pygame.Surface((Config.WIDTH, Config.HEIGHT))
            self._overlay_surf.set_alpha(180)
            self._overlay_surf.fill(p['bg'])
            
        surf.blit(self._overlay_surf, (0, 0))
        
        cx, cy = Config.WIDTH // 2, Config.HEIGHT // 2
        br = pygame.Rect(cx - 250, cy - 75, 500, 150)
        
        Graphics.draw_chamfered_rect(surf, br, p['fill'], 0)
        Graphics.draw_chamfered_rect(surf, br, p['accent'], 2)
        
        t = Assets.FONTS["BIG"].render(f"EXECUTING // {self.load_txt}", True, p['text'])
        surf.blit(t, (br.x + 30, br.y + 30))
        
        # Progress Bar
        pygame.draw.rect(surf, (10, 15, 20), (br.x + 30, br.y + 90, 440, 20))
        pygame.draw.rect(surf, p['accent'], (br.x + 30, br.y + 90, int(440 * self.vis_load_prog), 20))
        
        pc = Assets.FONTS["SUB"].render(f"{int(self.vis_load_prog * 100)}%", True, p['accent'])
        surf.blit(pc, (br.right - 60, br.y + 65))

class App:
    """
    Main Application Entry Point.
    
    Initializes the Pygame environment, manages the main game loop,
    and handles high-level state transitions (Login <-> Main Session).
    """

    def __init__(self) -> None:
        """Initialize the application window, load assets, and setup initial state."""
        Config.ensure_vault()
        pygame.init()
        Assets.load_fonts()
        
        self.screen = pygame.display.set_mode((Config.WIDTH, Config.HEIGHT), vsync=1)
        
        pygame.display.set_caption("HEXCORE // SECURE_TERM")
        self.clock = pygame.time.Clock()
        self.pidx = 0
        self.state = "LOGIN" 
        
        self.login_screen = LoginScreen()
        self.layout = LayoutManager()
        self.bg_hexes = [FloatingHex(Config.PALETTES[0]) for _ in range(30)]

    def toggle_theme(self) -> None:
        """
        Cycle through available visual themes.
        
        Updates the global palette index and refreshes cached graphics.
        """
        self.pidx = (self.pidx + 1) % len(Config.PALETTES)
        Graphics.clear_cache() # Clear grid cache on theme change
        for h in self.bg_hexes: h.reset(Config.PALETTES[self.pidx])

    def lock_system(self) -> None:
        """
        Return the application to the locked login state.
        
        Clears sensitive display data and resets the login input.
        """
        self.state = "LOGIN"
        self.login_screen.input_text = ""
        self.layout.log.set_important("SYSTEM LOCKED")
    
    def run(self) -> None:
        """Execute the main application event loop."""
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                
                if self.state == "LOGIN":
                    self.login_screen.handle(e, self)
                else:
                    self.layout.handle_input(e, self)
            
            for h in self.bg_hexes:
                h.update()
            
            if self.state == "LOGIN":
                self.login_screen.update()
            else:
                self.layout.update()
            
            p = Config.PALETTES[self.pidx]
            self.screen.fill(p['bg'])
            
            self.screen.blit(Graphics.get_dot_grid(p['dots']), (0,0))
            
            for h in self.bg_hexes: h.draw(self.screen)
            
            if self.state == "LOGIN":
                self.login_screen.draw(self.screen, p)
            else:
                self.layout.draw(self.screen, p)
            
            pygame.display.flip()
            self.clock.tick(Config.FPS)

if __name__ == "__main__":
    App().run()