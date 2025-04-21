import os
import json
import customtkinter as ctk
import vlc
from datetime import datetime, timedelta
from pathlib import Path
import configparser
import logging
import sys
from tkinter import filedialog, messagebox, font as tkfont # Added tkfont for font checking
import fitz  # PyMuPDF
from PIL import Image # Pillow
import time

# --- Constants ---
SUPPORTED_VIDEO_EXT = ('.mp4', '.mkv', '.avi', '.mov', '.wmv')
SUPPORTED_AUDIO_EXT = ('.mp3', '.wav', '.ogg', '.flac', '.aac')
SUPPORTED_PDF_EXT = ('.pdf',)
SUPPORTED_EXTENSIONS = SUPPORTED_VIDEO_EXT + SUPPORTED_AUDIO_EXT + SUPPORTED_PDF_EXT
TIMESTAMP_FILENAME = 'timestamps.json'
SETTINGS_FILENAME = 'library_settings.ini'
LOG_FILENAME = 'library_log.txt'
DEFAULT_LIBRARY_DIR_NAME = 'DigitalLibrary'
DEFAULT_NOTES_FONT_SIZE = 12 # Default font size for notes
DEFAULT_APPEARANCE_MODE = "System" # Default theme ('Light', 'Dark', 'System')
PDF_ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0] # Zoom levels

# --- Logging Setup ---
logging.basicConfig(
    filename=LOG_FILENAME,
    level=logging.INFO, # Changed default level to INFO, DEBUG can be noisy
    format='%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s',
    filemode='a' # Append to log file
)
# Also log to console for immediate feedback during development/debugging
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
logging.getLogger("vlc").setLevel(logging.WARNING) # Make VLC less noisy in logs


# --- Media Card (No significant changes needed here for these features) ---
class MediaCard(ctk.CTkFrame):
    def __init__(self, parent, file_path: Path, progress_data: dict | None, click_handler):
        super().__init__(parent, fg_color="#2b2b2b", corner_radius=8)
        self.grid_propagate(False) # Prevent frame from shrinking to content
        self.configure(width=220, height=180) # Slightly larger for better text fit

        self.file_path = file_path
        self.click_handler = click_handler

        # Title (filename)
        title = file_path.name
        title_label = ctk.CTkLabel(
            self,
            text=title,
            wraplength=200, # Adjusted wrap length
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        title_label.pack(pady=(10, 5), padx=10, fill="x")

        # Placeholder for content specific info (progress or PDF icon)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="x", padx=10, pady=5, expand=True)

        # --- Widgets for Audio/Video Progress ---
        self.progress_bar = ctk.CTkProgressBar(self.content_frame)
        self.time_label = ctk.CTkLabel(self.content_frame, text="0:00 / 0:00", font=("Arial", 10))
        self.last_played_label = ctk.CTkLabel(self.content_frame, text="", font=("Arial", 9))

        # --- Widget for PDF ---
        self.pdf_label = ctk.CTkLabel(self.content_frame, text="PDF Document", font=("Arial", 10, "italic"))

        # Determine card type and update display
        self.is_pdf = file_path.suffix.lower() in SUPPORTED_PDF_EXT
        self.update_display(progress_data)

        # Make the whole card clickable (bind to frame and children)
        self.bind("<Button-1>", self._on_click)
        title_label.bind("<Button-1>", self._on_click)
        self.content_frame.bind("<Button-1>", self._on_click)
        self.progress_bar.bind("<Button-1>", self._on_click)
        self.time_label.bind("<Button-1>", self._on_click)
        self.last_played_label.bind("<Button-1>", self._on_click)
        self.pdf_label.bind("<Button-1>", self._on_click)


    def _on_click(self, event=None):
        """Internal handler to call the main click handler."""
        self.click_handler(self.file_path)

    def update_display(self, progress_data: dict | None):
        """Update the card's display based on file type and progress."""
        # Hide all content widgets initially
        self.progress_bar.pack_forget()
        self.time_label.pack_forget()
        self.last_played_label.pack_forget()
        self.pdf_label.pack_forget()

        if self.is_pdf:
            self.pdf_label.pack(pady=10)
            # Update last opened for PDF? Could store this in timestamps.json too
            if progress_data and 'last_opened' in progress_data:
                 try:
                     last_opened = datetime.fromisoformat(progress_data['last_opened'])
                     last_opened_text = f"Last opened: {self.format_last_played(last_opened)}"
                     self.last_played_label.configure(text=last_opened_text)
                     self.last_played_label.pack(pady=(0, 5))
                 except (ValueError, TypeError):
                      self.last_played_label.configure(text="") # Reset if format is wrong
                      self.last_played_label.pack(pady=(0, 5))

        else: # Audio/Video
            self.progress_bar.pack(fill="x", pady=2)
            self.time_label.pack()
            self.last_played_label.pack(pady=(0, 5)) # Add padding below last played
            self.update_progress(progress_data)

    def update_progress(self, progress_data: dict | None):
        """Update progress bar, time label, and last played for A/V files."""
        if self.is_pdf: return # Don't update progress for PDFs here

        if progress_data:
            try:
                position = progress_data.get('position', 0)
                duration = progress_data.get('duration', 0)

                # Reset if duration is invalid
                if duration is None or duration <= 0: # More robust check
                    position = 0
                    duration = 0
                    self.progress_bar.set(0)
                    self.time_label.configure(text="0:00 / 0:00")
                else:
                    progress_pct = min(1.0, max(0.0, position / duration)) # Clamp between 0 and 1
                    self.progress_bar.set(progress_pct)
                    time_text = f"{self.format_time(position)} / {self.format_time(duration)}"
                    self.time_label.configure(text=time_text)

                # Update last played
                if 'last_played' in progress_data:
                     try:
                         last_played = datetime.fromisoformat(progress_data['last_played'])
                         last_played_text = f"Last played: {self.format_last_played(last_played)}"
                         self.last_played_label.configure(text=last_played_text)
                     except (ValueError, TypeError):
                         self.last_played_label.configure(text="") # Reset if format is wrong
                else:
                     self.last_played_label.configure(text="")

            except Exception as e:
                logging.error(f"Error updating card progress for {self.file_path.name}: {e}", exc_info=True)
                # Reset to default on error
                self.progress_bar.set(0)
                self.time_label.configure(text="0:00 / 0:00")
                self.last_played_label.configure(text="")
        else:
            # No progress data, set to default
            self.progress_bar.set(0)
            self.time_label.configure(text="0:00 / 0:00")
            self.last_played_label.configure(text="")

    def format_time(self, ms: int | float | None) -> str:
        if ms is None or ms < 0: ms = 0
        seconds = int(ms / 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def format_last_played(self, timestamp: datetime) -> str:
        now = datetime.now()
        diff = now - timestamp

        if diff < timedelta(minutes=1): return "just now"
        if diff < timedelta(hours=1): return f"{int(diff.total_seconds() / 60)} mins ago"
        if diff < timedelta(days=1): return f"{int(diff.total_seconds() / 3600)} hours ago"
        if diff < timedelta(days=7): return f"{diff.days} days ago"
        return timestamp.strftime("%Y-%m-%d")


# --- Main Application ---
class DigitalLibrary:
    def __init__(self):
        logging.info("--- Application Starting ---")
        self.window = ctk.CTk()
        self.window.title("Digital Library - 2.1 - Crist Yaghjian") # Version bump
        try:
            # Attempt to load icon, ignore if not found
            self.window.iconbitmap("icon.ico")
        except Exception:
            logging.warning("icon.ico not found, skipping.")
        self.window.geometry("1400x850") # Slightly larger default size
        # Appearance mode set after loading settings

        # --- State Variables ---
        self.library_path = Path.home() / DEFAULT_LIBRARY_DIR_NAME
        self.settings_file = Path(SETTINGS_FILENAME)
        self.timestamps_file = self.library_path / TIMESTAMP_FILENAME # Initial default, updated after settings load
        self.timestamps = {}
        self.config = configparser.ConfigParser()
        self.appearance_mode = DEFAULT_APPEARANCE_MODE
        self.notes_font_size = DEFAULT_NOTES_FONT_SIZE
        self.notes_font_family = "Helvetica" # Or allow config? Let's start with fixed family

        self.vlc_instance = None
        self.vlc_player = None
        self.current_vlc_media_path: Path | None = None
        self.is_vlc_playing = False

        self.pdf_doc: fitz.Document | None = None
        self.current_pdf_path: Path | None = None
        self.pdf_current_page_index = 0
        self.pdf_page_count = 0
        self.pdf_zoom_level = 1.0 # Initial zoom level
        self.pdf_image_label: ctk.CTkLabel | None = None # Label to display PDF page image
        self.pdf_viewer_frame: ctk.CTkScrollableFrame | None = None # *** CHANGED to ScrollableFrame ***
        self.pdf_controls_frame: ctk.CTkFrame | None = None # Frame holding PDF controls
        self.pdf_rendered_image: ctk.CTkImage | None = None # Keep reference to avoid GC issues

        self.media_controls_frame: ctk.CTkFrame | None = None # Frame holding A/V controls
        self.notes_file: Path | None = None
        self.notes_changed = False
        self.search_active = False

        self.active_media_type = None # 'video', 'audio', 'pdf', None

        # --- Initialization ---
        self.load_settings() # Load settings early
        ctk.set_appearance_mode(self.appearance_mode) # Apply loaded appearance mode
        ctk.set_default_color_theme("blue") # Keep theme consistent for now

        self.timestamps_file = self.library_path / TIMESTAMP_FILENAME # Update based on loaded settings
        self.timestamps = self.load_timestamps()
        self.initialize_vlc()

        # --- UI Setup ---
        self.setup_ui()
        self.load_library() # Load initial library view

        # --- Timers ---
        self.save_interval = 5000  # Save every 5 seconds
        self.progress_update_interval = 500 # Update progress bar faster
        self.card_update_interval = 5000 # Update all cards less frequently (5s)

        self.window.after(self.save_interval, self.periodic_save_timestamp)
        self.window.after(self.progress_update_interval, self.update_playback_progress)
        self.window.after(self.card_update_interval, self.update_all_cards_display)

        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        logging.info("Application Initialized Successfully")

    # --- Initialization & Configuration ---

    def load_settings(self):
        """Loads settings from the INI file."""
        logging.info(f"Loading settings from: {self.settings_file.resolve()}")
        try:
            defaults = {
                'library_path': str(Path.home() / DEFAULT_LIBRARY_DIR_NAME),
                'appearance_mode': DEFAULT_APPEARANCE_MODE,
                'notes_font_size': str(DEFAULT_NOTES_FONT_SIZE)
            }
            if self.settings_file.exists():
                self.config.read(self.settings_file)
                if 'Settings' not in self.config:
                    self.config['Settings'] = {} # Ensure section exists

                # Get library path
                loaded_path_str = self.config['Settings'].get('library_path', defaults['library_path'])
                loaded_path = Path(loaded_path_str)
                if loaded_path.is_dir():
                    self.library_path = loaded_path
                else:
                    logging.warning(f"Library path from settings not found: {loaded_path}. Using default/fallback.")
                    self.library_path = Path(defaults['library_path'])
                    self.config['Settings']['library_path'] = str(self.library_path) # Update config with fallback

                # Get appearance mode
                mode = self.config['Settings'].get('appearance_mode', defaults['appearance_mode']).capitalize()
                if mode in ["Light", "Dark", "System"]:
                    self.appearance_mode = mode
                else:
                    logging.warning(f"Invalid appearance mode '{mode}' in settings. Using default.")
                    self.appearance_mode = defaults['appearance_mode']
                    self.config['Settings']['appearance_mode'] = self.appearance_mode

                # Get notes font size
                try:
                    size = int(self.config['Settings'].get('notes_font_size', defaults['notes_font_size']))
                    if 6 <= size <= 72: # Reasonable font size range
                        self.notes_font_size = size
                    else:
                        raise ValueError("Font size out of range")
                except ValueError:
                    logging.warning(f"Invalid notes_font_size in settings. Using default.")
                    self.notes_font_size = int(defaults['notes_font_size'])
                    self.config['Settings']['notes_font_size'] = str(self.notes_font_size)

                # Save back any corrections/defaults applied during load
                self.save_config()

            else:
                logging.info("Settings file not found, creating default.")
                self._create_default_settings()

            # Ensure the library directory exists after loading/creating settings
            self.library_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Settings loaded: Path='{self.library_path}', Mode='{self.appearance_mode}', NotesFont={self.notes_font_size}")


        except (configparser.Error, OSError, Exception) as e:
            logging.error(f"Error loading or creating settings: {e}", exc_info=True)
            self.show_error("Settings Error", f"Could not load or create settings file '{self.settings_file.name}'. Using default settings.\nError: {e}")
            # Apply hardcoded defaults on severe error
            self.library_path = Path(defaults['library_path'])
            self.appearance_mode = defaults['appearance_mode']
            self.notes_font_size = int(defaults['notes_font_size'])
            self.library_path.mkdir(parents=True, exist_ok=True)
            # Try to create a minimal config in memory
            if 'Settings' not in self.config: self.config['Settings'] = {}
            self.config['Settings']['library_path'] = str(self.library_path)
            self.config['Settings']['appearance_mode'] = self.appearance_mode
            self.config['Settings']['notes_font_size'] = str(self.notes_font_size)

    def _create_default_settings(self):
        """Creates default settings and saves the file."""
        logging.debug("Creating default settings structure.")
        self.library_path = Path.home() / DEFAULT_LIBRARY_DIR_NAME
        self.library_path.mkdir(parents=True, exist_ok=True) # Ensure it exists
        self.appearance_mode = DEFAULT_APPEARANCE_MODE
        self.notes_font_size = DEFAULT_NOTES_FONT_SIZE

        self.config['Settings'] = {
            'library_path': str(self.library_path),
            'appearance_mode': self.appearance_mode,
            'notes_font_size': str(self.notes_font_size)
        }
        self.save_config()

    def save_config(self):
        """Saves the current config to the settings file."""
        logging.debug(f"Saving settings to: {self.settings_file.resolve()}")
        # Ensure current values are in the config object before writing
        if 'Settings' not in self.config: self.config['Settings'] = {}
        self.config['Settings']['library_path'] = str(self.library_path)
        self.config['Settings']['appearance_mode'] = self.appearance_mode
        self.config['Settings']['notes_font_size'] = str(self.notes_font_size)

        try:
            with open(self.settings_file, 'w') as f:
                self.config.write(f)
            logging.info("Settings saved successfully.")
        except (OSError, configparser.Error) as e:
            logging.error(f"Error saving settings: {e}", exc_info=True)
            self.show_error("Settings Save Error", f"Could not save settings file.\nError: {e}")

    # --- Timestamps (No change needed) ---
    def load_timestamps(self) -> dict:
        """Loads timestamps from the JSON file in the library directory."""
        logging.info(f"Loading timestamps from: {self.timestamps_file.resolve()}")
        if self.timestamps_file.exists():
            try:
                with open(self.timestamps_file, 'r') as f:
                    timestamps = json.load(f)
                logging.info(f"Loaded timestamps for {len(timestamps)} files.")
                # Convert keys (paths) back to Path objects if needed, though string keys are fine for dicts
                return timestamps
            except (json.JSONDecodeError, OSError, Exception) as e:
                logging.error(f"Error loading timestamps file '{self.timestamps_file.name}': {e}", exc_info=True)
                self.show_error("Timestamp Load Error", f"Could not load timestamps.\nError: {e}")
                return {}
        else:
            logging.info("Timestamps file not found. Starting fresh.")
            return {}

    def save_timestamps(self, timestamps_data: dict):
        """Saves the timestamps dictionary to the JSON file atomically."""
        logging.debug(f"Attempting to save {len(timestamps_data)} timestamps to: {self.timestamps_file.resolve()}")
        temp_file = self.timestamps_file.with_suffix('.json.tmp')
        try:
            # Ensure parent directory exists
            self.timestamps_file.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file first
            with open(temp_file, 'w') as f:
                json.dump(timestamps_data, f, indent=2)

            # Atomically replace the old file with the new one
            os.replace(temp_file, self.timestamps_file) # More atomic than remove/rename
            logging.debug(f"Timestamps saved successfully to {self.timestamps_file.name}")

        except (OSError, TypeError, Exception) as e:
            logging.error(f"Error saving timestamps: {e}", exc_info=True)
            # Don't show error popup for periodic saves, just log it.
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass # Ignore cleanup error

    # --- VLC (No change needed) ---
    def initialize_vlc(self):
        """Initializes the VLC instance and player."""
        logging.info("Initializing VLC")
        try:
            vlc_args = ['--no-video-title-show', '--quiet', '--ignore-config', '--no-plugins-cache', '--no-osd']
            self.vlc_instance = vlc.Instance(vlc_args)
            self.vlc_player = self.vlc_instance.media_player_new()
            logging.info("VLC initialized successfully.")
        except Exception as e:
            logging.critical(f"Failed to initialize VLC: {e}", exc_info=True)
            self.show_error("VLC Initialization Error", "Could not initialize VLC. Playback will not work. Ensure VLC is installed correctly.")
            self.vlc_instance = None
            self.vlc_player = None

    # --- UI Setup ---

    def setup_ui(self):
        logging.debug("Setting up UI elements.")
        # Main container partitioning
        self.window.grid_columnconfigure(0, weight=2) # Library list (narrower)
        self.window.grid_columnconfigure(1, weight=5) # Player/PDF viewer (wider)
        self.window.grid_columnconfigure(2, weight=3) # Notes (medium)
        self.window.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Library ---
        self.library_panel = ctk.CTkFrame(self.window, corner_radius=0)
        self.library_panel.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        self.library_panel.grid_rowconfigure(1, weight=1)
        self.library_panel.grid_columnconfigure(0, weight=1)

        # Search and Settings Bar
        self.search_frame = ctk.CTkFrame(self.library_panel)
        self.search_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.search_frame.grid_columnconfigure(0, weight=1)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add('write', self.filter_library)
        search_entry = ctk.CTkEntry(
            self.search_frame,
            textvariable=self.search_var,
            placeholder_text="Search library..."
        )
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=5)

        settings_button = ctk.CTkButton(
            self.search_frame,
            text="Settings",
            width=80,
            command=self.show_settings
        )
        settings_button.grid(row=0, column=1, padx=(5, 0), pady=5)

        # Scrollable frame for media cards
        self.scrollable_frame = ctk.CTkScrollableFrame(self.library_panel)
        self.scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.scrollable_frame.grid_columnconfigure(0, weight=1) # Allow cards to expand horizontally if needed

        # --- Center Panel: Player/Viewer ---
        self.player_panel = ctk.CTkFrame(self.window, corner_radius=0)
        self.player_panel.grid(row=0, column=1, sticky="nsew", padx=(2, 2), pady=5)
        self.player_panel.grid_rowconfigure(0, weight=1) # Viewer frame takes most space
        self.player_panel.grid_rowconfigure(1, weight=0) # Info label
        self.player_panel.grid_rowconfigure(2, weight=0) # Controls container
        self.player_panel.grid_columnconfigure(0, weight=1)

        # Container for Video or PDF display
        self.viewer_container = ctk.CTkFrame(self.player_panel, fg_color="black", corner_radius=0)
        self.viewer_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.viewer_container.grid_rowconfigure(0, weight=1)
        self.viewer_container.grid_columnconfigure(0, weight=1)

        # Video Frame (initially packed, managed later)
        self.video_frame = ctk.CTkFrame(self.viewer_container, fg_color="black", corner_radius=0)
        # Audio Placeholder Label (managed later)
        self.audio_placeholder = ctk.CTkLabel(self.viewer_container, text="Audio Playback", font=("Arial", 18, "italic"), text_color="gray")

        # *** PDF Viewer Frame (CHANGED TO SCROLLABLE) ***
        # This widget handles both vertical and horizontal scrollbars when needed.
        self.pdf_viewer_frame = ctk.CTkScrollableFrame(
            self.viewer_container,
            fg_color="transparent", # Background color for the scrollable area itself
            corner_radius=0,
            # label_text="PDF Viewer", # Optional label for the frame
            # label_fg_color=("gray70", "gray30") # Colors for the optional label
        )
        # Initially hidden, shown/packed via manage_views

        # *** PDF Image Label (placed INSIDE scrollable frame) ***
        # Use a background color for the label to simulate page background
        # Anchor it to the top-left corner so scrollbars work correctly when image is larger
        self.pdf_image_label = ctk.CTkLabel(
            self.pdf_viewer_frame, # Parent is the scrollable frame
            text="",
            corner_radius=0,
            fg_color="white" # Simulate page background
        )
        # Grid the label inside the scrollable frame's *internal* content area
        self.pdf_image_label.grid(row=0, column=0, sticky="nw", padx=0, pady=0)


        # Now Playing Info Label
        self.now_playing_label = ctk.CTkLabel(self.player_panel, text="No media selected", wraplength=450, anchor="w")
        self.now_playing_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 0))

        # --- Controls Container (Switches between A/V and PDF controls) ---
        self.controls_container = ctk.CTkFrame(self.player_panel, fg_color="transparent")
        self.controls_container.grid(row=2, column=0, sticky="ew", padx=5, pady=(0,5))
        self.controls_container.grid_columnconfigure(0, weight=1)

        # -- Media (A/V) Controls Frame --
        self.media_controls_frame = ctk.CTkFrame(self.controls_container, fg_color="transparent")
        self.media_controls_frame.grid(row=0, column=0, sticky="nsew") # Initially managed via grid_remove
        # Progress Bar and Time Label
        progress_time_frame = ctk.CTkFrame(self.media_controls_frame, fg_color="transparent")
        progress_time_frame.pack(fill="x", padx=5, pady=(0, 2))
        progress_time_frame.grid_columnconfigure(0, weight=1)
        self.time_label = ctk.CTkLabel(progress_time_frame, text="0:00 / 0:00")
        self.time_label.grid(row=0, column=1, sticky="e", padx=5) # Place time label next to slider
        self.media_progress_slider = ctk.CTkSlider(
            progress_time_frame, from_=0, to=100, command=self.on_media_slider_drag
        )
        # Bind release to actually perform the seek action for smoother UX
        self.media_progress_slider.bind("<ButtonRelease-1>", self.on_media_slider_release)
        self.media_progress_slider.grid(row=0, column=0, sticky="ew", padx=5)
        self.media_progress_slider.set(0) # Initialize slider

        # Buttons Frame
        media_buttons_frame = ctk.CTkFrame(self.media_controls_frame, fg_color="transparent")
        media_buttons_frame.pack(fill="x", padx=5, pady=(2, 5))
        # Adjust weights if speed menu takes more space
        media_buttons_frame.grid_columnconfigure((0, 1, 2), weight=1)
        media_buttons_frame.grid_columnconfigure(3, weight=0) # Speed menu fixed width

        skip_back_button = ctk.CTkButton(media_buttons_frame, text="-5s", width=60, command=lambda: self.skip_time(-5000))
        skip_back_button.grid(row=0, column=0, padx=2, sticky="e")
        self.play_pause_button = ctk.CTkButton(media_buttons_frame, text="Play", width=100, command=self.toggle_play_pause)
        self.play_pause_button.grid(row=0, column=1, padx=2)
        skip_fwd_button = ctk.CTkButton(media_buttons_frame, text="+5s", width=60, command=lambda: self.skip_time(5000))
        skip_fwd_button.grid(row=0, column=2, padx=2, sticky="w")

        # Speed Control
        speeds = ["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "1.75x", "2.0x", "2.5x", "3.0x"]
        self.speed_var = ctk.StringVar(value="1.0x")
        speed_menu = ctk.CTkOptionMenu(
            media_buttons_frame, values=speeds, variable=self.speed_var, command=self.change_playback_speed, width=100
        )
        speed_menu.grid(row=0, column=3, padx=10, sticky="e") # Aligned right

        # -- PDF Controls Frame --
        self.pdf_controls_frame = ctk.CTkFrame(self.controls_container, fg_color="transparent")
        self.pdf_controls_frame.grid(row=0, column=0, sticky="nsew") # Initially managed via grid_remove
        # Updated grid for zoom buttons
        self.pdf_controls_frame.grid_columnconfigure((0, 4), weight=1) # Edge buttons push inwards
        self.pdf_controls_frame.grid_columnconfigure((1, 2, 3), weight=0) # Center elements fixed width

        pdf_prev_button = ctk.CTkButton(self.pdf_controls_frame, text="< Prev", width=80, command=self.pdf_previous_page)
        pdf_prev_button.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        pdf_zoom_out_button = ctk.CTkButton(self.pdf_controls_frame, text="-", width=40, command=self.pdf_zoom_out)
        pdf_zoom_out_button.grid(row=0, column=1, padx=(5, 2), pady=5)

        self.pdf_page_label = ctk.CTkLabel(self.pdf_controls_frame, text="Page 0 / 0", width=100)
        self.pdf_page_label.grid(row=0, column=2, padx=2, pady=5) # Centered between zoom buttons

        pdf_zoom_in_button = ctk.CTkButton(self.pdf_controls_frame, text="+", width=40, command=self.pdf_zoom_in)
        pdf_zoom_in_button.grid(row=0, column=3, padx=(2, 5), pady=5)

        pdf_next_button = ctk.CTkButton(self.pdf_controls_frame, text="Next >", width=80, command=self.pdf_next_page)
        pdf_next_button.grid(row=0, column=4, padx=5, pady=5, sticky="w")


        # --- Right Panel: Notes ---
        self.notes_panel = ctk.CTkFrame(self.window, corner_radius=0)
        self.notes_panel.grid(row=0, column=2, sticky="nsew", padx=(2, 5), pady=5)
        self.notes_panel.grid_rowconfigure(2, weight=1) # Text area takes most space
        self.notes_panel.grid_columnconfigure(0, weight=1)

        # Notes Toolbar
        self.notes_toolbar = ctk.CTkFrame(self.notes_panel)
        self.notes_toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.notes_toolbar.grid_columnconfigure((0, 1, 2), weight=1) # Distribute buttons

        new_note_button = ctk.CTkButton(self.notes_toolbar, text="New", command=self.new_notes)
        new_note_button.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        open_note_button = ctk.CTkButton(self.notes_toolbar, text="Open", command=self.open_notes)
        open_note_button.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        save_note_button = ctk.CTkButton(self.notes_toolbar, text="Save", command=self.save_notes)
        save_note_button.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        # Current Notes File Label
        self.notes_file_label = ctk.CTkLabel(self.notes_panel, text="Untitled", wraplength=280, anchor="w")
        self.notes_file_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        # Notes Text Area
        notes_font_config = (self.notes_font_family, self.notes_font_size)
        self.notes_text = ctk.CTkTextbox(self.notes_panel, wrap="word", font=notes_font_config, border_width=1)
        self.notes_text.grid(row=2, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.notes_text.bind("<<Modified>>", self.on_notes_modified)
        self.update_notes_font() # Ensure font is applied

        # --- Initial View Management ---
        self.manage_views(None) # Start with no media active view
    # --- Library Management (No change needed) ---
    def load_library(self):
        """Clears and reloads the library view based on the current library_path."""
        logging.info(f"Loading library from: {self.library_path}")
        # Clear existing cards
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # Reset grid configuration (important if number of columns changes)
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.scrollable_frame.grid_columnconfigure(1, weight=0) # Reset extra columns
        self.scrollable_frame.grid_columnconfigure(2, weight=0)

        media_files = []
        try:
            if not self.library_path.is_dir():
                logging.warning(f"Library path is not a valid directory: {self.library_path}")
                self.show_error("Library Error", f"The library path is not valid:\n{self.library_path}\nPlease check Settings.")
                return

            for item in self.library_path.rglob('*'): # Recursively search
                if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                     media_files.append(item)

        except OSError as e:
            logging.error(f"Error scanning library directory {self.library_path}: {e}", exc_info=True)
            self.show_error("Library Scan Error", f"Could not read the library directory.\nError: {e}")
            return

        # Sort files alphabetically for consistent order
        media_files.sort(key=lambda x: x.name.lower()) # Case-insensitive sort
        logging.info(f"Found {len(media_files)} supported media files.")

        # Create cards in a grid layout
        max_cols = 2 # Adjust number of columns based on desired card width and panel width
        self.scrollable_frame.grid_columnconfigure(list(range(max_cols)), weight=1)

        for i, file_path in enumerate(media_files):
            row = i // max_cols
            col = i % max_cols
            # Pass the string representation of the path for JSON key lookup
            progress_data = self.timestamps.get(str(file_path))

            card = MediaCard(
                self.scrollable_frame,
                file_path,
                progress_data,
                self.handle_media_click # Use the unified handler
            )
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        self.search_active = False # Reset search flag

    def filter_library(self, *args):
        """Filters the library view based on the search term."""
        search_term = self.search_var.get().lower().strip()
        is_cleared = not search_term and self.search_active
        is_new_search = bool(search_term)

        if is_cleared:
            logging.debug("Search cleared, reloading full library.")
            self.load_library() # Reloads all and resets search_active
            return
        elif not is_new_search: # No search term and not previously active
             return

        logging.debug(f"Filtering library for term: '{search_term}'")
        self.search_active = True

        # Clear existing cards
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # Reset grid configuration
        max_cols = 2
        self.scrollable_frame.grid_columnconfigure(list(range(max_cols)), weight=1)

        row, col = 0, 0
        found_count = 0
        try:
            if not self.library_path.is_dir():
                logging.warning("Library path invalid during search.")
                return # Or show error

            # Iterate and filter - use sorted list for consistency
            all_files = sorted(
                [item for item in self.library_path.rglob('*')
                 if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS],
                key=lambda x: x.name.lower()
            )

            for item in all_files:
                if search_term in item.name.lower():
                    progress_data = self.timestamps.get(str(item))
                    card = MediaCard(
                        self.scrollable_frame,
                        item,
                        progress_data,
                        self.handle_media_click
                    )
                    card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                    col += 1
                    found_count += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
            logging.debug(f"Found {found_count} items matching search.")

        except OSError as e:
            logging.error(f"Error scanning library during filter {self.library_path}: {e}", exc_info=True)


    # --- Media Handling ---

    def handle_media_click(self, file_path: Path):
        """Determines media type and calls the appropriate load function."""
        logging.info(f"Media clicked: {file_path.name}")

        # Save state of currently playing media *before* switching
        self.stop_and_save_current_media() # Handles both VLC and PDF cleanup

        file_ext = file_path.suffix.lower()

        if file_ext in SUPPORTED_VIDEO_EXT or file_ext in SUPPORTED_AUDIO_EXT:
            self.active_media_type = 'video' if file_ext in SUPPORTED_VIDEO_EXT else 'audio'
            self.load_vlc_media(file_path)
        elif file_ext in SUPPORTED_PDF_EXT:
            self.active_media_type = 'pdf'
            self.load_pdf_media(file_path)
        else:
            logging.warning(f"Clicked on unsupported file type: {file_path.name}")
            self.show_error("Unsupported File", f"Cannot open file type: {file_ext}")
            self.active_media_type = None
            self.manage_views(None)

        # Update the "Now Playing" label
        self.now_playing_label.configure(text=f"Selected: {file_path.name}")


    def load_vlc_media(self, file_path: Path):
        """Loads and plays audio/video file using VLC."""
        if not self.vlc_player or not self.vlc_instance:
            logging.error("VLC not initialized, cannot play media.")
            self.show_error("Playback Error", "VLC is not available. Cannot play media.")
            return

        logging.info(f"Loading VLC media: {file_path.name} (Type: {self.active_media_type})")
        try:
            # Ensure previous media is fully stopped/released before loading new one
            if self.vlc_player.get_media():
                 self.vlc_player.stop() # Stop playback
                 # Optionally release the media object, though set_media should handle it
                 # current_media = self.vlc_player.get_media()
                 # if current_media: current_media.release()

            media = self.vlc_instance.media_new(str(file_path)) # VLC needs string path
            # Optional: Add media options if needed (e.g., network caching)
            # media.add_option(f':network-caching={1000}') # Example
            self.vlc_player.set_media(media)
            self.current_vlc_media_path = file_path # Store Path object

            # --- Embed Video Output ---
            # Must be done *before* playing on some platforms
            if self.active_media_type == 'video':
                self.manage_views('video') # Show video frame *before* setting HWND
                # Allow UI to update to ensure frame ID is valid
                self.window.update_idletasks()
                try:
                    win_id = self.video_frame.winfo_id()
                    if sys.platform.startswith('win'):
                        self.vlc_player.set_hwnd(win_id)
                    elif sys.platform.startswith('darwin'): # macOS
                        # Setting NSView directly is complex, often needs library specific calls (like PyQt/Kivy)
                        # Or might work via ctypes if VLC provides the right function binding.
                        # Let's try set_nsobject if available, otherwise log warning.
                        try:
                            # self.vlc_player.set_nsobject(win_id) # Needs correct casting/object
                            # For now, likely opens external window on Mac if embedding fails easily
                            logging.warning("Direct video embedding on macOS may require additional setup or open externally.")
                        except AttributeError:
                             logging.warning("VLC binding lacks set_nsobject, embedding may fail on macOS.")
                    else: # Linux/X11
                        self.vlc_player.set_xwindow(win_id)
                    logging.debug(f"Attempted to set video output to window ID: {win_id}")
                except Exception as e:
                     logging.error(f"Failed to set video output: {e}", exc_info=True)
                     # Don't show error popup here, VLC might still play audio or open externally
                     self.manage_views('audio') # Fallback to audio view if embedding fails visually

            elif self.active_media_type == 'audio':
                self.manage_views('audio') # Show audio placeholder

            # --- Start Playback ---
            if self.vlc_player.play() == -1:
                 logging.error("VLC failed to start playback.")
                 self.show_error("Playback Error", f"Could not start playback for {file_path.name}.")
                 self.current_vlc_media_path = None
                 self.manage_views(None)
                 return

            self.is_vlc_playing = True
            self.play_pause_button.configure(text="Pause")

            # --- Restore Position and Speed ---
            # Delay slightly to allow media to load its duration
            self.window.after(300, self._restore_vlc_state) # Increased delay slightly

        except Exception as e:
            logging.error(f"Error loading or playing VLC media '{file_path.name}': {e}", exc_info=True)
            self.show_error("Playback Error", f"Could not play file.\nError: {e}")
            self.current_vlc_media_path = None
            self.is_vlc_playing = False
            self.play_pause_button.configure(text="Play")
            self.manage_views(None)


    def _restore_vlc_state(self):
        """Internal function to restore position and speed after media loads."""
        if not self.vlc_player or not self.current_vlc_media_path or not self.vlc_player.get_media():
            logging.debug("Restore state called but player/media not ready.")
            return

        try:
            # Wait until duration is available (or timeout)
            duration = 0
            wait_attempts = 0
            max_attempts = 30 # ~3 seconds max wait

            while duration <= 0 and wait_attempts < max_attempts:
                duration = self.vlc_player.get_length()
                if duration > 0:
                    break
                wait_attempts += 1
                # Yield control briefly to allow VLC events to process
                # Use after instead of time.sleep to keep UI responsive
                self.window.after(100) # Wait 100ms
                self.window.update() # Force UI update


            if duration <= 0:
                logging.warning(f"Could not get media duration for {self.current_vlc_media_path.name} after ~{max_attempts*100}ms.")
                # Proceed without restoring position if duration is unknown

            # Restore position
            media_key = str(self.current_vlc_media_path)
            saved_time_ms = 0
            if media_key in self.timestamps:
                saved_data = self.timestamps[media_key]
                # Check for valid dict and keys defensively
                if isinstance(saved_data, dict) and 'position' in saved_data and isinstance(saved_data['position'], (int, float)):
                    saved_time_ms = saved_data['position']
                    saved_duration = saved_data.get('duration', 0)
                    # Sanity check: If saved duration differs wildly from current, maybe don't restore position?
                    # Or only restore if position is valid within *current* duration
                    if duration > 0 and 0 < saved_time_ms < duration:
                        logging.info(f"Restoring position for {self.current_vlc_media_path.name} to {self.format_time(saved_time_ms)}")
                        self.vlc_player.set_time(int(saved_time_ms))
                    elif saved_time_ms <= 0:
                        logging.debug("Saved position is 0 or less, starting from beginning.")
                    else: # saved_time_ms >= duration
                         logging.warning(f"Saved position {saved_time_ms}ms is beyond current duration {duration}ms. Starting from beginning.")
                         self.vlc_player.set_time(0) # Start from beginning
                else:
                    logging.debug(f"No valid position data found in timestamps for {self.current_vlc_media_path.name}.")
            else:
                logging.debug(f"No timestamp entry found for {self.current_vlc_media_path.name}. Starting from beginning.")

            # Restore playback speed (ensure player is playing or paused, not stopped)
            current_state = self.vlc_player.get_state()
            if current_state in [vlc.State.Playing, vlc.State.Paused]:
                 self.change_playback_speed(self.speed_var.get())
            else:
                 logging.debug("Player not in playing/paused state, skipping speed restore for now.")


        except Exception as e:
            logging.error(f"Error restoring VLC state: {e}", exc_info=True)


    def load_pdf_media(self, file_path: Path):
        """Loads a PDF file using PyMuPDF."""
        logging.info(f"Loading PDF: {file_path.name}")
        try:
            # Close previous PDF if open
            if self.pdf_doc:
                self.pdf_doc.close()
                self.pdf_doc = None

            self.pdf_doc = fitz.open(file_path)
            self.current_pdf_path = file_path
            self.pdf_page_count = len(self.pdf_doc)
            self.pdf_current_page_index = 0
            self.pdf_zoom_level = 1.0 # Reset zoom on new PDF load

             # Store last opened time
            media_key = str(self.current_pdf_path)
            if media_key not in self.timestamps: self.timestamps[media_key] = {}
            self.timestamps[media_key]['last_opened'] = datetime.now().isoformat()
            self.timestamps[media_key]['filename'] = self.current_pdf_path.name # Store filename for consistency
            # Could also store last viewed page index / zoom level here if desired
            # self.timestamps[media_key]['pdf_page'] = self.pdf_current_page_index
            # self.timestamps[media_key]['pdf_zoom'] = self.pdf_zoom_level
            self.save_timestamps(self.timestamps) # Save immediately after opening

            if self.pdf_page_count > 0:
                self.manage_views('pdf') # Show PDF view
                # Render the first page after a short delay to allow UI layout
                self.window.after(50, lambda: self.render_pdf_page(self.pdf_current_page_index))
            else:
                logging.warning(f"PDF file '{file_path.name}' has no pages.")
                self.show_error("PDF Error", "The selected PDF file appears to be empty.")
                self.pdf_doc.close()
                self.pdf_doc = None
                self.current_pdf_path = None
                self.manage_views(None)

        except Exception as e:
            logging.error(f"Error loading PDF '{file_path.name}': {e}", exc_info=True)
            self.show_error("PDF Load Error", f"Could not open PDF file.\nError: {e}")
            if self.pdf_doc:
                self.pdf_doc.close()
            self.pdf_doc = None
            self.current_pdf_path = None
            self.active_media_type = None
            self.manage_views(None)


    def stop_and_save_current_media(self):
        """Stops playback or closes PDF and saves state."""
        logging.debug("Stopping and saving current media state.")
        if self.vlc_player and self.current_vlc_media_path:
            current_state = self.vlc_player.get_state()
            if current_state in [vlc.State.Playing, vlc.State.Paused]:
                self.save_current_vlc_timestamp() # Save position before stopping
                try:
                    self.vlc_player.stop()
                    logging.debug("VLC playback stopped.")
                except Exception as e:
                    logging.warning(f"Error stopping VLC player: {e}")
            elif current_state != vlc.State.Stopped and current_state != vlc.State.NothingSpecial and current_state != vlc.State.Ended:
                 # If in an opening/buffering state, try to stop anyway
                 try:
                     self.vlc_player.stop()
                     logging.debug("VLC playback stopped (was in intermediate state).")
                 except Exception as e:
                     logging.warning(f"Error stopping VLC player (intermediate state): {e}")

            self.is_vlc_playing = False
            # Don't nullify current_vlc_media_path here, it might be needed immediately after (e.g., for card update)
            # Let the next load/action nullify it if necessary.
            self.play_pause_button.configure(text="Play")
            self.media_progress_slider.set(0)
            self.time_label.configure(text="0:00 / 0:00")


        if self.pdf_doc and self.current_pdf_path:
            # Save last viewed page index and zoom?
            media_key = str(self.current_pdf_path)
            if media_key in self.timestamps:
               # Ensure data is a dict before adding keys
               if not isinstance(self.timestamps[media_key], dict): self.timestamps[media_key] = {}
               self.timestamps[media_key]['pdf_page'] = self.pdf_current_page_index
               self.timestamps[media_key]['pdf_zoom'] = self.pdf_zoom_level
               self.save_timestamps(self.timestamps)
            try:
                self.pdf_doc.close()
                logging.debug("PDF document closed.")
            except Exception as e:
                 logging.warning(f"Error closing PDF document: {e}")
            self.pdf_doc = None
            # self.current_pdf_path = None # Keep path until next media loaded?
            self.pdf_page_count = 0
            self.pdf_current_page_index = 0
            # Clear the image label
            if self.pdf_image_label:
                self.pdf_image_label.configure(image=None)
                self.pdf_rendered_image = None


        # Reset active type after handling specifics
        self.active_media_type = None
        # Don't manage views here, let the calling function decide the next view


    def manage_views(self, view_type: str | None):
        """Shows/hides the correct viewer (Video, Audio placeholder, PDF) and controls."""
        logging.debug(f"Managing views for type: {view_type}")

        # --- Manage Viewer Area (Use pack for simplicity here, grid for controls) ---
        self.video_frame.pack_forget()
        self.audio_placeholder.pack_forget()
        self.pdf_viewer_frame.pack_forget() # Use pack_forget for the scrollable frame too

        if view_type == 'video':
            self.video_frame.pack(fill="both", expand=True)
            logging.debug("Showing video frame.")
        elif view_type == 'audio':
            self.audio_placeholder.pack(fill="both", expand=True, padx=20, pady=20) # Center placeholder
            logging.debug("Showing audio placeholder.")
        elif view_type == 'pdf':
            self.pdf_viewer_frame.pack(fill="both", expand=True) # Pack the scrollable frame
            logging.debug("Showing PDF viewer frame.")
        else: # None or other
             logging.debug("Hiding all media viewer frames.")
             # Clear any lingering PDF image
             if self.pdf_image_label:
                 self.pdf_image_label.configure(image=None)
                 self.pdf_rendered_image = None

        # --- Manage Controls Area (Using grid) ---
        self.media_controls_frame.grid_remove() # Use grid_remove to keep grid config
        self.pdf_controls_frame.grid_remove()

        if view_type == 'video' or view_type == 'audio':
            self.media_controls_frame.grid() # Show media controls
            logging.debug("Showing media controls.")
        elif view_type == 'pdf':
            self.pdf_controls_frame.grid() # Show PDF controls
            logging.debug("Showing PDF controls.")
        else:
            logging.debug("Hiding all controls.")
            pass # Both already hidden


    # --- Playback Controls (VLC) ---

    def toggle_play_pause(self):
        """Toggles play/pause state of the VLC player."""
        if not self.vlc_player or not self.current_vlc_media_path:
            logging.warning("Play/Pause toggle attempted with no media loaded.")
            return

        try:
            if self.vlc_player.is_playing():
                self.vlc_player.pause()
                self.play_pause_button.configure(text="Play")
                self.is_vlc_playing = False
                logging.debug("VLC paused.")
                # Save timestamp immediately on pause
                self.save_current_vlc_timestamp()
            else:
                # Check if we are at the end, if so, restart from beginning (or last saved pos?)
                current_state = self.vlc_player.get_state()
                if current_state == vlc.State.Ended:
                     logging.debug("Media ended, restarting playback.")
                     self.vlc_player.stop() # Stop first
                     self.window.after(50, self._restart_playback) # Restart after small delay
                elif self.vlc_player.play() == -1:
                     logging.error("VLC failed to resume/start playback.")
                     # Handle error - maybe reset state?
                     self.show_error("Playback Error", "VLC failed to play.")
                     return
                else: # Started playing successfully
                    self.play_pause_button.configure(text="Pause")
                    self.is_vlc_playing = True
                    logging.debug("VLC playing.")
        except Exception as e:
            logging.error(f"Error during toggle play/pause: {e}", exc_info=True)

    def _restart_playback(self):
        """Helper to restart playback, potentially restoring position."""
        if self.vlc_player and self.current_vlc_media_path:
             if self.vlc_player.play() != -1:
                 self.is_vlc_playing = True
                 self.play_pause_button.configure(text="Pause")
                 self._restore_vlc_state() # Attempt to restore state (might start from beginning if no timestamp)
             else:
                  logging.error("Failed to restart playback after media ended.")

    def skip_time(self, ms_offset: int):
        """Skips forward or backward in the current VLC media."""
        if self.vlc_player and self.current_vlc_media_path and self.vlc_player.is_seekable():
            try:
                current_time = self.vlc_player.get_time()
                duration = self.vlc_player.get_length()
                new_time = current_time + ms_offset
                # Clamp time between 0 and duration (if known)
                if duration > 0:
                    new_time = max(0, min(new_time, duration - 100)) # Don't seek exactly to end
                else:
                    new_time = max(0, new_time)

                self.vlc_player.set_time(new_time)
                logging.debug(f"Skipped time by {ms_offset}ms to {new_time}ms")
                # Update slider immediately for responsiveness
                self.update_playback_progress(force_update=True) # Force visual update
            except Exception as e:
                logging.error(f"Error skipping time: {e}", exc_info=True)
        elif self.vlc_player and not self.vlc_player.is_seekable():
            logging.warning("Cannot skip time: media is not seekable.")

    def change_playback_speed(self, speed_str: str):
        """Changes the playback speed of the VLC player."""
        if self.vlc_player and self.current_vlc_media_path:
            try:
                speed_value = float(speed_str.replace('x', ''))
                # Ensure player is in a state where rate can be set
                current_state = self.vlc_player.get_state()
                if current_state in [vlc.State.Playing, vlc.State.Paused]:
                    if self.vlc_player.set_rate(speed_value) == 0: # set_rate returns 0 on success
                        logging.info(f"Playback speed changed to {speed_value}x")
                    else:
                        logging.warning(f"Failed to set playback speed to {speed_value}x")
                        # Reset the OptionMenu variable if setting fails?
                        current_rate = self.vlc_player.get_rate()
                        self.speed_var.set(f"{current_rate:.2f}x".replace('.00x','x').replace('.50x','.5x').replace('.25x','.25x').replace('.75x','.75x'))

                else:
                    logging.debug(f"Player not playing/paused ({current_state}), deferring speed change.")
                    # Store desired speed? Or just apply next time play starts? For now, just log.
            except ValueError:
                logging.error(f"Invalid speed format: {speed_str}")
            except Exception as e:
                logging.error(f"Error changing playback speed: {e}", exc_info=True)

    def on_media_slider_drag(self, value_str: str):
        """Handles visual update while user is dragging the progress slider."""
        # This function is called continuously while dragging.
        # Only update the time label visually, don't seek yet.
        if not self.vlc_player or not self.current_vlc_media_path: return

        try:
            value = float(value_str)
            duration = self.vlc_player.get_length()
            if duration > 0:
                target_time = int((value / 100.0) * duration)
                # Update time label only
                self.time_label.configure(text=f"{self.format_time(target_time)} / {self.format_time(duration)}")
            else:
                self.time_label.configure(text=f"??:?? / ??:??")
        except ValueError:
            pass # Ignore non-float values during drag

    def on_media_slider_release(self, event=None):
        """Handles the actual seek when the user releases the progress slider."""
        if not self.vlc_player or not self.current_vlc_media_path or not self.vlc_player.is_seekable():
            return

        try:
            value = self.media_progress_slider.get() # Get final value from slider
            duration = self.vlc_player.get_length()
            if duration > 0:
                target_time = int((value / 100.0) * duration)
                logging.debug(f"Slider seek (on release) to {value:.1f}% ({target_time}ms)")
                self.vlc_player.set_time(target_time)
                # Update time label and maybe card immediately
                self.update_playback_progress(force_update=True)
                # If paused, save timestamp after seek
                if not self.is_vlc_playing:
                     self.save_current_vlc_timestamp()
            else:
                 # If duration unknown, seeking by percentage is meaningless
                 logging.warning("Cannot seek using slider: media duration unknown.")
                 # Update progress normally to reflect current state
                 self.update_playback_progress()

        except ValueError:
            logging.error(f"Invalid slider value on release: {self.media_progress_slider.get()}")
        except Exception as e:
             logging.error(f"Error seeking with slider on release: {e}", exc_info=True)
             # Update progress normally to reflect current state
             self.update_playback_progress()


    # --- PDF Controls ---

    def render_pdf_page(self, page_index: int, force_render=False):
        """Renders a specific PDF page to the pdf_image_label, considering zoom."""
        if not self.pdf_doc or not self.pdf_image_label or not self.pdf_viewer_frame:
            logging.warning("PDF components not available for rendering.")
            return

        if not (0 <= page_index < self.pdf_page_count):
            logging.warning(f"Invalid page index requested: {page_index}. Count: {self.pdf_page_count}")
            return

        # Avoid re-rendering the same page at the same zoom unless forced
        if page_index == self.pdf_current_page_index and not force_render:
            # Check if zoom has changed, if so, force re-render anyway
             # (Handled by zoom functions calling this with force_render=True)
             # logging.debug(f"Skipping render for same page index {page_index}")
             pass # Allow zoom check below or just proceed if zoom changed

        logging.debug(f"Rendering PDF page index: {page_index} at zoom: {self.pdf_zoom_level:.2f}")
        # Optional: Show a 'loading' indicator?
        # self.pdf_image_label.configure(text="Loading page...", image=None)
        # self.window.update_idletasks() # Show message immediately

        try:
            page = self.pdf_doc.load_page(page_index)

            # --- Render page to image with zoom ---
            matrix = fitz.Matrix(self.pdf_zoom_level, self.pdf_zoom_level)
            pix = page.get_pixmap(matrix=matrix, alpha=False) # Render without alpha for simplicity/speed?

            # Convert fitz pixmap to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Create CTkImage - Use the *actual* rendered size from pixmap
            # No downscaling here - let the scrollable frame handle large images
            self.pdf_rendered_image = ctk.CTkImage(
                light_image=img,
                dark_image=img, # Use same image for both modes unless specific logic is added
                size=(pix.width, pix.height)
            )

            # Update the label
            self.pdf_image_label.configure(image=self.pdf_rendered_image, text="") # Clear any previous text

            # Update state *after* successful rendering
            self.pdf_current_page_index = page_index
            self.update_pdf_page_indicator()

            # Scroll the view back to the top-left after loading a new page/zoom
            # Might need a slight delay for layout to settle?
            self.window.after(10, lambda: self.pdf_viewer_frame._parent_canvas.yview_moveto(0))
            self.window.after(10, lambda: self.pdf_viewer_frame._parent_canvas.xview_moveto(0))


            logging.debug(f"PDF page {page_index + 1} displayed (Size: {pix.width}x{pix.height}).")

        except Exception as e:
            logging.error(f"Error rendering PDF page {page_index}: {e}", exc_info=True)
            self.pdf_image_label.configure(image=None, text=f"Error rendering page {page_index + 1}")
            self.pdf_rendered_image = None


    def pdf_next_page(self):
        """Goes to the next page of the PDF."""
        if self.pdf_doc and self.pdf_current_page_index < self.pdf_page_count - 1:
            self.render_pdf_page(self.pdf_current_page_index + 1, force_render=True) # Force re-render for new page
        else:
            logging.debug("Already on the last PDF page.")

    def pdf_previous_page(self):
        """Goes to the previous page of the PDF."""
        if self.pdf_doc and self.pdf_current_page_index > 0:
            self.render_pdf_page(self.pdf_current_page_index - 1, force_render=True) # Force re-render for new page
        else:
             logging.debug("Already on the first PDF page.")

    def pdf_zoom_in(self):
        """Increases the PDF zoom level."""
        if not self.pdf_doc: return
        try:
            current_zoom_index = PDF_ZOOM_STEPS.index(self.pdf_zoom_level)
            if current_zoom_index < len(PDF_ZOOM_STEPS) - 1:
                self.pdf_zoom_level = PDF_ZOOM_STEPS[current_zoom_index + 1]
                self.render_pdf_page(self.pdf_current_page_index, force_render=True)
            else:
                logging.debug("Already at maximum PDF zoom.")
        except ValueError:
             # If current zoom isn't exactly in steps, find nearest and go up
             logging.warning(f"Current zoom {self.pdf_zoom_level} not in steps. Finding next step.")
             for step in PDF_ZOOM_STEPS:
                 if step > self.pdf_zoom_level:
                     self.pdf_zoom_level = step
                     self.render_pdf_page(self.pdf_current_page_index, force_render=True)
                     return
             # If already >= max step, do nothing
             logging.debug("Already at or above maximum PDF zoom step.")


    def pdf_zoom_out(self):
        """Decreases the PDF zoom level."""
        if not self.pdf_doc: return
        try:
            current_zoom_index = PDF_ZOOM_STEPS.index(self.pdf_zoom_level)
            if current_zoom_index > 0:
                self.pdf_zoom_level = PDF_ZOOM_STEPS[current_zoom_index - 1]
                self.render_pdf_page(self.pdf_current_page_index, force_render=True)
            else:
                logging.debug("Already at minimum PDF zoom.")
        except ValueError:
             # If current zoom isn't exactly in steps, find nearest and go down
             logging.warning(f"Current zoom {self.pdf_zoom_level} not in steps. Finding previous step.")
             for step in reversed(PDF_ZOOM_STEPS):
                 if step < self.pdf_zoom_level:
                     self.pdf_zoom_level = step
                     self.render_pdf_page(self.pdf_current_page_index, force_render=True)
                     return
             # If already <= min step, do nothing
             logging.debug("Already at or below minimum PDF zoom step.")

    def update_pdf_page_indicator(self):
        """Updates the label showing the current page number and zoom."""
        if self.pdf_doc:
            zoom_percent = int(self.pdf_zoom_level * 100)
            self.pdf_page_label.configure(text=f"Page {self.pdf_current_page_index + 1}/{self.pdf_page_count} ({zoom_percent}%)")
        else:
            self.pdf_page_label.configure(text="Page - / -")


    # --- Progress Updates & Saving ---

    def update_playback_progress(self, force_update=False):
        """Periodically updates the progress slider and time label for VLC media."""
        # Check if the slider is currently being pressed by the user
        #winfo_containing is not reliable across platforms/toolkits.
        # A simple flag could work: set flag on <ButtonPress>, clear on <ButtonRelease> on slider.
        # For now, we rely on the fact that on_media_slider_release triggers the actual seek.
        # The periodic update here might slightly conflict visually during drag, but functionally okay.

        if self.vlc_player and self.current_vlc_media_path and (self.is_vlc_playing or force_update):
            try:
                current_time = self.vlc_player.get_time()
                duration = self.vlc_player.get_length()

                if duration is not None and duration > 0:
                    progress_percent = min(100, max(0,(current_time / duration) * 100.0)) # Clamp percentage
                    # Update slider *only if not being actively dragged* (heuristic: check if playing)
                    # Or always update if force_update is True
                    if self.is_vlc_playing or force_update:
                        self.media_progress_slider.set(progress_percent)

                    self.time_label.configure(
                        text=f"{self.format_time(current_time)} / {self.format_time(duration)}"
                    )
                elif current_time is not None: # Duration might be unknown initially
                    self.media_progress_slider.set(0)
                    self.time_label.configure(text=f"{self.format_time(current_time)} / --:--")
                else: # Both unknown / error state
                     self.media_progress_slider.set(0)
                     self.time_label.configure(text="0:00 / 0:00")


            except Exception as e:
                # This can happen if media is suddenly closed or errors out
                logging.debug(f"Could not update playback progress: {e}")
                # Reset on error? Only if the media path still seems valid.
                if self.current_vlc_media_path:
                    self.media_progress_slider.set(0)
                    self.time_label.configure(text="0:00 / 0:00")

        # Schedule next update (only if not forced)
        if not force_update:
             self.window.after(self.progress_update_interval, self.update_playback_progress)


    def periodic_save_timestamp(self):
        """Periodically saves the timestamp for the currently playing VLC media."""
        if self.vlc_player and self.current_vlc_media_path and self.is_vlc_playing:
             # Only save if actively playing, pause/stop saves timestamp immediately
             self.save_current_vlc_timestamp()

        # Schedule next periodic save
        self.window.after(self.save_interval, self.periodic_save_timestamp)


    def save_current_vlc_timestamp(self):
        """Saves the current position, duration, and last played time for VLC media."""
        if not self.vlc_player or not self.current_vlc_media_path:
            return

        try:
            # Ensure we have a valid media object associated with the player
            if not self.vlc_player.get_media():
                 logging.debug("No media in player, skipping timestamp save.")
                 return

            current_time_ms = self.vlc_player.get_time()
            duration_ms = self.vlc_player.get_length()

            # Only save meaningful progress
            # Check state too: Don't save if 'Stopped', 'Error', 'Ended' unless specifically handled
            current_state = self.vlc_player.get_state()
            should_save = current_state in [vlc.State.Playing, vlc.State.Paused]

            # Allow saving position=0 if duration is known (e.g., paused at start)
            if should_save and duration_ms is not None and duration_ms >= 0 and current_time_ms is not None and current_time_ms >= 0:
                 # Check if position is near the end, maybe mark as 'finished'?
                 is_finished = (duration_ms > 0 and current_time_ms >= duration_ms - 2000) # Within 2s of end

                 media_key = str(self.current_vlc_media_path) # Use string path as key
                 timestamp_data = {
                    'position': 0 if is_finished else current_time_ms, # Store 0 if finished
                    'duration': duration_ms,
                    'last_played': datetime.now().isoformat(),
                    'filename': self.current_vlc_media_path.name, # Store filename for reference
                    'finished': is_finished # Optional flag
                 }
                 # Update the main timestamps dictionary only if data changed significantly?
                 # For simplicity, always update if saving is triggered.
                 self.timestamps[media_key] = timestamp_data
                 # Save the entire dictionary
                 self.save_timestamps(self.timestamps)
                 logging.debug(f"Saved timestamp for {self.current_vlc_media_path.name}: pos={timestamp_data['position']}ms / dur={duration_ms}ms (Finished: {is_finished})")
            else:
                 logging.debug(f"Skipping timestamp save for {self.current_vlc_media_path.name} (time={current_time_ms}, duration={duration_ms}, state={current_state})")

        except Exception as e:
            logging.error(f"Error saving VLC timestamp: {e}", exc_info=True)


    def update_all_cards_display(self):
        """Periodically updates the display of all visible media cards."""
        logging.debug("Updating all visible card displays.")
        current_media_key_vlc = str(self.current_vlc_media_path) if self.current_vlc_media_path else None
        current_media_key_pdf = str(self.current_pdf_path) if self.current_pdf_path else None

        # Update timestamp for currently playing/paused VLC media *first* in memory
        # This ensures cards show the most recent data if the periodic save hasn't run yet
        if self.vlc_player and current_media_key_vlc:
             state = self.vlc_player.get_state()
             if state in [vlc.State.Playing, vlc.State.Paused]:
                 try:
                     current_time = self.vlc_player.get_time()
                     duration = self.vlc_player.get_length()
                     if duration is not None and duration >= 0 and current_time is not None and current_time >= 0:
                         is_finished = (duration > 0 and current_time >= duration - 2000)
                         self.timestamps[current_media_key_vlc] = {
                             'position': 0 if is_finished else current_time,
                             'duration': duration,
                             'last_played': datetime.now().isoformat(), # Update last played time
                             'filename': self.current_vlc_media_path.name,
                             'finished': is_finished
                         }
                 except Exception as e:
                     logging.warning(f"Failed to get current progress for card update: {e}")

        # Update last opened time for currently open PDF
        if self.pdf_doc and current_media_key_pdf:
             if current_media_key_pdf not in self.timestamps: self.timestamps[current_media_key_pdf] = {}
             if isinstance(self.timestamps[current_media_key_pdf], dict): # Ensure it's a dict
                 self.timestamps[current_media_key_pdf]['last_opened'] = datetime.now().isoformat()
                 self.timestamps[current_media_key_pdf]['filename'] = self.current_pdf_path.name
                 # Update page/zoom if storing them
                 # self.timestamps[current_media_key_pdf]['pdf_page'] = self.pdf_current_page_index
                 # self.timestamps[current_media_key_pdf]['pdf_zoom'] = self.pdf_zoom_level


        # Update cards in the scrollable frame
        widgets_to_update = list(self.scrollable_frame.winfo_children()) # Get list to avoid issues if modified during loop
        for widget in widgets_to_update:
            if isinstance(widget, MediaCard):
                 card_media_key = str(widget.file_path)
                 progress_data = self.timestamps.get(card_media_key)
                 widget.update_display(progress_data) # Use update_display which handles type

        # Schedule next update
        self.window.after(self.card_update_interval, self.update_all_cards_display)


    # --- Notes Functionality ---

    def update_notes_font(self):
        """Applies the configured font size to the notes textbox."""
        try:
            new_font = (self.notes_font_family, self.notes_font_size)
            # Check if font is available (optional but good practice)
            # available_fonts = tkfont.families()
            # if self.notes_font_family not in available_fonts:
            #     logging.warning(f"Notes font family '{self.notes_font_family}' not found, using system default.")
            #     new_font = (None, self.notes_font_size) # Use default family

            if self.notes_text:
                self.notes_text.configure(font=new_font)
            logging.debug(f"Notes font updated to: {new_font}")
        except Exception as e:
            logging.error(f"Failed to update notes font: {e}", exc_info=True)

    def on_notes_modified(self, event=None):
        """Callback when the notes text is modified."""
        # The <<Modified>> event fires frequently. Check the actual flag.
        try:
            # Check if the widget still exists before accessing edit_modified
            if self.notes_text.winfo_exists() and self.notes_text.edit_modified():
                if not self.notes_changed: # Mark changed only once until saved
                    self.notes_changed = True
                    logging.debug("Notes modified.")
                    self._update_notes_title_indicator(unsaved=True)
                # Reset the internal Tkinter modified flag after checking it
                self.notes_text.edit_modified(False)
        except Exception as e:
             logging.warning(f"Error in on_notes_modified (possibly during shutdown): {e}")


    def _update_notes_title_indicator(self, unsaved: bool):
        """Adds or removes the '*' indicator from the notes title."""
        base_title = os.path.basename(self.notes_file) if self.notes_file else "Untitled"
        display_title = f"{base_title}{'*' if unsaved else ''}"
        if self.notes_file_label: # Check if label exists
            self.notes_file_label.configure(text=display_title)

    def new_notes(self):
        """Creates a new, empty note, prompting if current notes are unsaved."""
        logging.info("Creating new note.")
        if self.notes_changed:
            if not self._confirm_discard_note_changes():
                return # User cancelled

        if self.notes_text:
            self.notes_text.delete("1.0", "end")
            self.notes_file = None
            self.notes_changed = False
            self.notes_text.edit_modified(False) # Reset modified flag
            self._update_notes_title_indicator(unsaved=False)
            logging.debug("New note created.")

    def open_notes(self):
        """Opens a text file into the notes editor, prompting if current notes are unsaved."""
        logging.info("Opening note.")
        if self.notes_changed:
            if not self._confirm_discard_note_changes():
                return # User cancelled

        # Use asksaveasfilename for 'Open' as well
        file_path_str = filedialog.askopenfilename(
            title="Open Note File",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
            initialdir= str(self.library_path) # Start in library dir
        )

        if file_path_str:
            file_path = Path(file_path_str)
            logging.debug(f"Attempting to open note: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                if self.notes_text:
                    self.notes_text.delete("1.0", "end")
                    self.notes_text.insert("1.0", content)
                    self.notes_file = file_path
                    self.notes_changed = False
                    self.notes_text.edit_modified(False) # Reset modified flag
                    self._update_notes_title_indicator(unsaved=False)
                    logging.info(f"Note opened successfully: {file_path.name}")
            except (OSError, UnicodeDecodeError, Exception) as e:
                logging.error(f"Error opening note file {file_path}: {e}", exc_info=True)
                self.show_error("Error Opening File", f"Could not open the selected file.\nError: {e}")

    def save_notes(self):
        """Saves the current notes, prompting for a filename if it's a new note."""
        logging.info("Saving note.")
        if not self.notes_file:
            # Prompt for save location if file doesn't exist yet
            file_path_str = filedialog.asksaveasfilename(
                 title="Save Note As",
                 defaultextension=".txt",
                 filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
                 initialdir= str(self.library_path), # Start in library dir
                 initialfile= "Untitled.txt"
            )
            if not file_path_str:
                logging.debug("Save As cancelled by user.")
                return False # Indicate save failed/cancelled
            self.notes_file = Path(file_path_str)
            logging.debug(f"New note file path chosen: {self.notes_file}")

        # Proceed with saving
        try:
            if not self.notes_text:
                 logging.error("Notes text widget does not exist, cannot save.")
                 return False
            content = self.notes_text.get("1.0", "end-1c") # Get content excluding final newline
            with open(self.notes_file, 'w', encoding='utf-8') as file:
                file.write(content)
            self.notes_changed = False
            self.notes_text.edit_modified(False) # Reset modified flag after save
            self._update_notes_title_indicator(unsaved=False)
            logging.info(f"Note saved successfully: {self.notes_file.name}")
            return True # Indicate save successful
        except (OSError, Exception) as e:
            logging.error(f"Error saving note file {self.notes_file}: {e}", exc_info=True)
            self.show_error("Error Saving File", f"Could not save the notes file.\nError: {e}")
            return False # Indicate save failed


    def _confirm_discard_note_changes(self) -> bool:
        """Asks the user if they want to discard unsaved notes changes. Returns True if okay to proceed, False to cancel."""
        logging.debug("Confirming discard of unsaved note changes.")
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes in the current note. Do you want to save them?",
             icon=messagebox.WARNING,
             parent=self.window # Ensure message box is parented correctly
        )
        if response is True: # Yes (Save)
            logging.debug("User chose to save note changes.")
            return self.save_notes() # Proceed only if save was successful
        elif response is False: # No (Discard)
            logging.debug("User chose to discard note changes.")
            return True # Okay to proceed (discard)
        else: # Cancel
            logging.debug("User cancelled operation.")
            return False # Do not proceed

    # --- Settings ---

    def show_settings(self):
        """Displays the settings window."""
        logging.debug("Showing settings window.")
        settings_window = ctk.CTkToplevel(self.window)
        settings_window.title("Settings")
        settings_window.geometry("600x350") # Increased height for new options
        settings_window.transient(self.window) # Keep on top of main window
        settings_window.grab_set() # Modal behavior
        settings_window.resizable(False, False)

        settings_window.grid_columnconfigure(0, weight=1)
        settings_window.grid_rowconfigure(5, weight=1) # Push buttons to bottom

        # --- Library Path ---
        ctk.CTkLabel(settings_window, text="Library Folder Path:").grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 0), sticky="w")
        current_path_var = ctk.StringVar(value=str(self.library_path))
        path_entry = ctk.CTkEntry(settings_window, textvariable=current_path_var, width=400)
        path_entry.grid(row=1, column=0, padx=(20, 5), pady=5, sticky="ew")

        def browse_directory():
            dir_path = filedialog.askdirectory(initialdir=str(self.library_path), title="Select Library Folder", parent=settings_window)
            if dir_path:
                current_path_var.set(dir_path)
                logging.debug(f"Directory browsed: {dir_path}")

        browse_button = ctk.CTkButton(settings_window, text="Browse...", command=browse_directory, width=100)
        browse_button.grid(row=1, column=1, padx=(0, 20), pady=5, sticky="w")

        # --- Appearance Mode ---
        ctk.CTkLabel(settings_window, text="Appearance Mode:").grid(row=2, column=0, columnspan=2, padx=20, pady=(15, 0), sticky="w")
        appearance_var = ctk.StringVar(value=self.appearance_mode)
        appearance_options = ["Light", "Dark", "System"]
        appearance_menu = ctk.CTkOptionMenu(settings_window, variable=appearance_var, values=appearance_options, width=150)
        appearance_menu.grid(row=3, column=0, padx=20, pady=5, sticky="w")

        # --- Notes Font Size ---
        ctk.CTkLabel(settings_window, text="Notes Font Size:").grid(row=2, column=1, padx=20, pady=(15, 0), sticky="w")
        font_size_var = ctk.StringVar(value=str(self.notes_font_size))
        font_size_entry = ctk.CTkEntry(settings_window, textvariable=font_size_var, width=80)
        font_size_entry.grid(row=3, column=1, padx=(20, 5), pady=5, sticky="w")
        # Could use an OptionMenu for font size too if preferred


        # --- Save and Cancel Buttons ---
        button_frame = ctk.CTkFrame(settings_window, fg_color="transparent")
        button_frame.grid(row=6, column=0, columnspan=2, pady=(20, 15)) # Use row 6 to push down

        def apply_settings():
            # --- Apply Library Path ---
            new_path_str = current_path_var.get().strip()
            path_changed = False
            logging.info(f"Settings Apply: Path='{new_path_str}', Mode='{appearance_var.get()}', Font='{font_size_var.get()}'")

            if not new_path_str:
                 self.show_error("Invalid Path", "Library path cannot be empty.", parent=settings_window)
                 return
            new_path = Path(new_path_str)

            if not new_path.is_dir():
                try:
                    if messagebox.askyesno("Create Directory?", f"The directory '{new_path}' does not exist.\nDo you want to create it?", parent=settings_window):
                        new_path.mkdir(parents=True, exist_ok=True)
                        logging.info(f"Created new library directory: {new_path}")
                    else:
                        logging.info("User chose not to create non-existent directory.")
                        current_path_var.set(str(self.library_path)) # Revert entry to old path
                        # Do not return yet, allow other settings to be applied
                except OSError as e:
                     logging.error(f"Failed to create directory {new_path}: {e}", exc_info=True)
                     self.show_error("Error Creating Directory", f"Could not create the directory.\n{e}", parent=settings_window)
                     return # Stop applying settings on this error

            # Check if path actually changed and is now valid
            if new_path.is_dir() and new_path != self.library_path:
                logging.info(f"Library path change detected: '{self.library_path}' -> '{new_path}'")
                path_changed = True
                # Stop current media *before* changing paths
                self.stop_and_save_current_media()
                # Clear viewer and controls
                self.manage_views(None)
                self.now_playing_label.configure(text="No media selected")
                # Update configuration
                self.library_path = new_path
            # --- Apply Appearance Mode ---
            new_mode = appearance_var.get()
            if new_mode != self.appearance_mode:
                logging.info(f"Appearance mode changed to: {new_mode}")
                self.appearance_mode = new_mode
                ctk.set_appearance_mode(self.appearance_mode) # Apply immediately

            # --- Apply Notes Font Size ---
            try:
                new_size_str = font_size_var.get().strip()
                new_size = int(new_size_str)
                if not (6 <= new_size <= 72):
                     raise ValueError("Font size out of range 6-72")
                if new_size != self.notes_font_size:
                     logging.info(f"Notes font size changed to: {new_size}")
                     self.notes_font_size = new_size
                     self.update_notes_font() # Apply immediately
            except ValueError as e:
                 logging.warning(f"Invalid font size entered: '{new_size_str}'. Error: {e}")
                 self.show_error("Invalid Font Size", "Please enter a number between 6 and 72 for the notes font size.", parent=settings_window)
                 font_size_var.set(str(self.notes_font_size)) # Revert entry
                 # Do not return, allow other settings to save


            # --- Save Config and Reload Library if path changed ---
            self.save_config() # Save all applied settings

            if path_changed:
                # Update timestamp file path *based on the new library path*
                self.timestamps_file = self.library_path / TIMESTAMP_FILENAME
                # Reload timestamps from the *new* location
                self.timestamps = self.load_timestamps() # Crucial: reload timestamps
                # Reload the library view from the new path
                self.load_library()

            settings_window.destroy()


        save_button = ctk.CTkButton(button_frame, text="Save & Close", command=apply_settings)
        save_button.pack(side="left", padx=10)

        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=settings_window.destroy, fg_color="gray", hover_color="dark gray")
        cancel_button.pack(side="left", padx=10)

    # --- Utility and Cleanup ---

    def show_error(self, title: str, message: str, parent = None):
        """Displays an error message box using CTkToplevel for consistency."""
        logging.error(f"Showing Error - Title: {title}, Message: {message}")
        try:
            # Use the window that is currently active or the main window
            active_window = parent or self.window.focus_get() or self.window

            error_win = ctk.CTkToplevel(active_window)
            error_win.title(title)
            error_win.geometry("400x170") # Slightly taller
            error_win.transient(active_window)
            error_win.grab_set()
            error_win.after(10, error_win.lift) # Ensure it's on top

            error_win.grid_columnconfigure(0, weight=1)
            error_win.grid_rowconfigure(0, weight=1)

            msg_label = ctk.CTkLabel(error_win, text=message, wraplength=360, justify="left")
            msg_label.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

            ok_button = ctk.CTkButton(error_win, text="OK", command=error_win.destroy, width=80)
            ok_button.grid(row=1, column=0, pady=(0, 15))

            error_win.after(20, error_win.grab_set) # Re-grab focus after widgets added

        except Exception as e:
             # Fallback if CTkTopLevel fails for some reason
             logging.error(f"Fallback error display triggered: {e}")
             messagebox.showerror(title, message, parent=parent or self.window)


    def format_time(self, ms: int | float | None) -> str:
        # Keep using the static method from MediaCard for consistency
        return MediaCard.format_time(None, ms)


    def on_close(self):
        """Handles application closing, saves state, releases resources."""
        logging.info("--- Application Closing ---")

        # 1. Check for unsaved notes
        if self.notes_changed:
            if not self._confirm_discard_note_changes():
                logging.info("Application close cancelled by user (unsaved notes).")
                return # Abort closing

        # 2. Stop and save current media state (VLC/PDF)
        logging.debug("Stopping media and saving final state before exit.")
        self.stop_and_save_current_media() # This saves the final timestamp/PDF state

        # 3. Cancel pending 'after' calls to prevent errors during shutdown
        # Basic approach: Find specific timer IDs if possible, otherwise this is complex.
        # For now, rely on checks within the timer functions (e.g., if self.window exists)
        # Or simply let them error out quietly during shutdown if necessary.
        logging.debug("Skipping explicit cancellation of 'after' timers.")


        # 4. Release VLC resources (important!)
        if self.vlc_player:
            try:
                # Check state before releasing
                if self.vlc_player.get_state() != vlc.State.NothingSpecial:
                     if self.vlc_player.is_playing():
                         self.vlc_player.stop() # Ensure stopped before release
                self.vlc_player.release()
                logging.info("VLC player released.")
            except Exception as e:
                 logging.warning(f"Error releasing VLC player: {e}")
            self.vlc_player = None
        if self.vlc_instance:
             try:
                 self.vlc_instance.release()
                 logging.info("VLC instance released.")
             except Exception as e:
                 logging.warning(f"Error releasing VLC instance: {e}")
             self.vlc_instance = None

        # 5. Final save of all timestamps (usually redundant, but safe)
        logging.debug("Performing final timestamp save.")
        self.save_timestamps(self.timestamps)

        # 6. Save settings (in case something changed programmatically without explicit save)
        logging.debug("Performing final settings save.")
        self.save_config()

        # 7. Destroy the main window
        logging.info("Destroying main window.")
        try:
            self.window.destroy()
        except Exception as e:
             logging.warning(f"Error destroying main window: {e}")

        logging.info("--- Application Closed ---")
        # Force exit if Tkinter hangs? (Use cautiously)
        # sys.exit(0)

    def run(self):
        """Starts the main application loop."""
        logging.info("Starting main application loop.")
        try:
            self.window.mainloop()
        except Exception as e:
            logging.critical(f"Unhandled exception in main loop: {e}", exc_info=True)
            # Optionally try to show a final error message
            # self.show_error("Fatal Error", f"An unexpected error occurred:\n{e}")


if __name__ == "__main__":
    # Set high DPI awareness for Windows (place *before* CTk app creation)
    try:
        if sys.platform == "win32":
             import ctypes
             ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
             logging.info("Set High DPI awareness for Windows.")
    except Exception as e:
        logging.warning(f"Could not set High DPI awareness: {e}")

    try:
        app = DigitalLibrary()
        app.run()
    except Exception as main_exception:
         # Log any exceptions that occur *during* initialization before mainloop
         logging.critical(f"Critical error during application startup: {main_exception}", exc_info=True)
         # Try to show a simple Tkinter error box if GUI setup failed early
         try:
             import tkinter as tk
             root = tk.Tk()
             root.withdraw() # Hide the empty root window
             messagebox.showerror("Application Startup Error", f"Failed to initialize the application.\nPlease check '{LOG_FILENAME}' for details.\n\nError: {main_exception}")
             root.destroy()
         except Exception as tk_error:
             print(f"FATAL: Could not display Tkinter error message: {tk_error}")
             print(f"FATAL STARTUP ERROR: {main_exception}") # Print to console as last resort
         sys.exit(1) # Exit with error code