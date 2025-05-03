import streamlit as st
import os
import shutil
import subprocess
import platform
import re
import math # For file size conversion

# --- Configuration ---
PREDEFINED_PATHS = {
    "Model Material": r"\\Skdla-sa-nas01\skdla-sa\3Shape Design Output\Model Material",
    "Exocad": r"\\Skdla-sa-nas01\skdla-sa\CAD-Data -- Exocad",
    "InHouse Printing": r"\\KDC-LABSERVER\CadCam\! INHOUSE PRINTING !", # New Path
}
MODEL_BASE_PATH = r"\\KDC-LABSERVER\CadCam\! INHOUSE PRINTING !\.MODELS"
TISSUE_BASE_PATH = r"\\KDC-LABSERVER\CadCam\! INHOUSE PRINTING !\TISSUE"
INHOUSE_PRINTING_PATH = PREDEFINED_PATHS.get("InHouse Printing") # Store for easy access

# --- Exocad Specific Keywords ---
EXOCAD_ALLOWED_KEYWORDS = {"modelbase", "model", "tissue", "gingiva"}
EXOCAD_TISSUE_KEYWORDS = {"modelgingiva", "tissue", "gingiva"}
EXOCAD_SOURCE_PATH = PREDEFINED_PATHS.get("Exocad")

# --- Keywords for Model Size Display ---
MODEL_DISPLAY_SIZE_KEYWORDS = {"model", "antag", "tooth", "teeth", "die", "modelbase"}

SIZE_LIMIT_MB = 620.0
SIZE_LIMIT_BYTES = SIZE_LIMIT_MB * 1024 * 1024

# --- Helper Functions ---

def search_top_level_folders(root_dir, search_term):
    """Searches for top-level folders using os.scandir()."""
    found_folders = []
    search_term_lower = search_term.lower()
    if not os.path.isdir(root_dir): return found_folders
    try:
        with os.scandir(root_dir) as it:
            for entry in it:
                if search_term_lower in entry.name.lower():
                    try:
                        if entry.is_dir(): found_folders.append((entry.name, entry.path))
                    except OSError: pass
    except (PermissionError, FileNotFoundError, OSError): return []
    return found_folders

def search_files_recursively(root_dir, search_terms):
    """
    Recursively searches for STL files containing any search term within root_dir.
    Returns a list of matching file paths.
    """
    found_files = []
    if not search_terms or not os.path.isdir(root_dir):
        return found_files
    search_terms_lower = {term.lower() for term in search_terms}

    try:
        for root, dirs, files in os.walk(root_dir):
            # Skip hidden directories or specific ones if needed
            # dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith('.stl'):
                    # Check if any search term is in the filename
                    if any(term in file_lower for term in search_terms_lower):
                        found_files.append(os.path.join(root, file))
    except OSError as e:
        st.error(f"Error searching in {root_dir}: {e}")
    except Exception as e:
        st.error(f"Unexpected error during file search: {e}")
    return found_files

def get_recursive_folder_details(folder_paths_dict):
    """
    Recursively finds files, calculates total copy size and display model size (non-tissue only),
    checks for non-STL, and checks if any tissue/gingiva STL files are present.
    Input: folder_paths_dict = {folder_path: origin_label}
    """
    all_top_level_folders = list(folder_paths_dict.keys())
    total_copy_size_bytes = 0 # Size of STLs that WILL be copied
    display_model_size_bytes = 0 # Size of non-tissue STLs matching display keywords
    non_stl_found = False
    tissue_files_present = False
    empty_folders_encountered = []

    for folder_path, origin_label in folder_paths_dict.items():
        items_in_this_folder = 0
        is_exocad_origin = (origin_label == "Exocad" and EXOCAD_SOURCE_PATH and folder_path.startswith(EXOCAD_SOURCE_PATH))

        try:
            if not os.path.isdir(folder_path):
                empty_folders_encountered.append(folder_path)
                continue

            for root, dirs, files in os.walk(folder_path):
                items_in_this_folder += len(dirs) + len(files)
                for file in files:
                    file_path = os.path.join(root, file)
                    file_lower = file.lower()
                    try:
                        current_file_size = os.path.getsize(file_path)

                        is_stl = file_lower.endswith('.stl')
                        if not is_stl:
                            non_stl_found = True
                            continue # Skip further checks for non-STL

                        # --- Apply Exocad Filter ---
                        should_process_stl = True
                        if is_exocad_origin:
                            if not any(keyword in file_lower for keyword in EXOCAD_ALLOWED_KEYWORDS):
                                should_process_stl = False

                        if should_process_stl:
                            # Add size to total copy size (this file passed filters)
                            total_copy_size_bytes += current_file_size

                            # --- Determine if tissue FIRST ---
                            is_tissue_file = False
                            if is_exocad_origin and any(keyword in file_lower for keyword in EXOCAD_TISSUE_KEYWORDS):
                                is_tissue_file = True
                            elif not is_exocad_origin and ("tissue" in file_lower or "gingiva" in file_lower):
                                is_tissue_file = True

                            if is_tissue_file:
                                tissue_files_present = True
                            else:
                                # --- If NOT tissue, check for display keywords ---
                                if any(keyword in file_lower for keyword in MODEL_DISPLAY_SIZE_KEYWORDS):
                                    display_model_size_bytes += current_file_size

                    except OSError: pass # Ignore files we can't access/get size

            if items_in_this_folder == 0 and os.path.isdir(folder_path):
                 empty_folders_encountered.append(folder_path)

        except OSError as e:
            empty_folders_encountered.append(folder_path)

    # Return the updated sizes along with others
    return all_top_level_folders, total_copy_size_bytes, display_model_size_bytes, non_stl_found, tissue_files_present, list(set(empty_folders_encountered))

def get_file_details(file_paths):
    """
    Analyzes a list of FILE paths. Calculates total size and display model size.
    Note: Tissue/Non-STL checks aren't strictly needed here as destination is fixed.
    """
    total_copy_size_bytes = 0
    display_model_size_bytes = 0
    non_stl_found = False # Should ideally be only STLs, but check anyway
    tissue_files_present = False # Check for info display

    for file_path in file_paths:
        file_lower = os.path.basename(file_path).lower()
        try:
            current_file_size = os.path.getsize(file_path)
            total_copy_size_bytes += current_file_size # All found files contribute to total

            if not file_lower.endswith('.stl'):
                non_stl_found = True # Should not happen if search is correct
                continue

            # Check for display keywords
            if any(keyword in file_lower for keyword in MODEL_DISPLAY_SIZE_KEYWORDS):
                display_model_size_bytes += current_file_size

            # Check for tissue keywords for info display
            if "tissue" in file_lower or "gingiva" in file_lower:
                 tissue_files_present = True

        except OSError:
            st.warning(f"Could not get size for: {file_path}")
            pass # Ignore files we can't access

    # Return values consistent with get_recursive_folder_details where applicable
    return file_paths, total_copy_size_bytes, display_model_size_bytes, non_stl_found, tissue_files_present, [] # No 'empty folders' in this mode

# --- MODIFIED copy_items function ---
def copy_items(items_to_process, search_mode, open_destination=False):
    """
    Copies items based on the search mode. Ensures final status message appears only after completion.
    """
    if not items_to_process:
        st.warning("No items selected or found to copy.")
        return

    copied_stl_count = 0
    error_count = 0
    total_stl_to_copy = 0 # Initialize
    current_copied_count = 0 # Initialize here for broader scope

    # --- FOLDER SEARCH MODE ---
    if search_mode == 'folder':
        source_folders_dict = items_to_process
        # Read settings from session state
        model_copy_mode = st.session_state.get('model_copy_mode', 'Directly into Base')
        model_subfolder_name = st.session_state.get('model_new_folder_name', '').strip()
        tissue_copy_mode = st.session_state.get('tissue_copy_mode', 'Directly into Base')
        tissue_subfolder_name = st.session_state.get('tissue_new_folder_name', '').strip()
        tissue_files_found_in_analysis = st.session_state.get('tissue_files_found_in_selection', False)

        # Validate base paths and necessary subfolder names
        model_base_valid = os.path.isdir(MODEL_BASE_PATH)
        tissue_base_valid = os.path.isdir(TISSUE_BASE_PATH) if tissue_files_found_in_analysis else True
        if not model_base_valid: st.error(f"Model Folder Destination invalid: {MODEL_BASE_PATH}"); return
        if not tissue_base_valid and tissue_files_found_in_analysis: st.error(f"Tissue Destination invalid: {TISSUE_BASE_PATH}"); return
        if model_copy_mode == 'Into a New Subfolder' and not is_valid_foldername(model_subfolder_name): st.error(f"Invalid Model subfolder name."); return
        if tissue_files_found_in_analysis and tissue_copy_mode == 'Into a New Subfolder' and not is_valid_foldername(tissue_subfolder_name): st.error(f"Invalid Tissue subfolder name."); return

        scan_status = st.empty()
        with st.spinner("Scanning folders for STL files to copy..."):
            for folder_path, origin_label in source_folders_dict.items():
                is_exocad_origin_scan = (origin_label == "Exocad" and EXOCAD_SOURCE_PATH and folder_path.startswith(EXOCAD_SOURCE_PATH))
                scan_status.text(f"Scanning: {os.path.basename(folder_path)}...")
                try:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_lower = file.lower()
                            if file_lower.endswith('.stl'):
                                if is_exocad_origin_scan:
                                    if any(keyword in file_lower for keyword in EXOCAD_ALLOWED_KEYWORDS): total_stl_to_copy += 1
                                else: total_stl_to_copy += 1
                except OSError as e: st.warning(f"Could not fully scan {folder_path}: {e}")
            scan_status.text(f"Found {total_stl_to_copy} STL files matching criteria.")

        if total_stl_to_copy == 0: st.warning("No '.stl' files matching criteria found."); scan_status.empty(); return

        progress_bar = st.progress(0); status_text = st.empty()
        final_status_placeholder = st.empty() # Create placeholder for final message
        status_text.text("Starting STL file copy..."); final_destination_paths_used = set();

        for folder_path, origin_label in source_folders_dict.items():
            is_exocad_origin = (origin_label == "Exocad" and EXOCAD_SOURCE_PATH and folder_path.startswith(EXOCAD_SOURCE_PATH))
            try:
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_lower = file.lower()
                        if file_lower.endswith('.stl'):
                            should_copy_this_stl = True
                            if is_exocad_origin and not any(keyword in file_lower for keyword in EXOCAD_ALLOWED_KEYWORDS):
                                should_copy_this_stl = False
                            if not should_copy_this_stl: continue

                            source_file_path = os.path.join(root, file); is_tissue_file = False
                            if is_exocad_origin and any(keyword in file_lower for keyword in EXOCAD_TISSUE_KEYWORDS): is_tissue_file = True
                            elif not is_exocad_origin and ("tissue" in file_lower or "gingiva" in file_lower): is_tissue_file = True

                            if is_tissue_file:
                                current_base_path = TISSUE_BASE_PATH; current_copy_mode = tissue_copy_mode; current_subfolder_name = tissue_subfolder_name
                            else:
                                current_base_path = MODEL_BASE_PATH; current_copy_mode = model_copy_mode; current_subfolder_name = model_subfolder_name

                            if current_copy_mode == 'Into a New Subfolder': target_dir = os.path.join(current_base_path, current_subfolder_name)
                            else: target_dir = current_base_path

                            destination_file_path = os.path.join(target_dir, file) # Original filename
                            status_text.text(f"Copying: {file} ({current_copied_count+1}/{total_stl_to_copy})") # Update progress text
                            try:
                                os.makedirs(target_dir, exist_ok=True); final_destination_paths_used.add(target_dir)
                                shutil.copy2(source_file_path, destination_file_path); current_copied_count += 1
                            except (shutil.Error, OSError, Exception) as e: st.error(f"Error copying '{file}' to '{target_dir}': {e}"); error_count += 1
                            finally:
                                if total_stl_to_copy > 0: progress_bar.progress(current_copied_count / total_stl_to_copy)
            except OSError as e: st.error(f"Error walking folder {folder_path}: {e}"); error_count += 1

    # --- FILE SEARCH MODE ---
    elif search_mode == 'file':
        source_file_paths = items_to_process
        copy_mode = st.session_state.get('model_copy_mode', 'Directly into Base') # Reuse model mode
        subfolder_name = st.session_state.get('model_new_folder_name', '').strip() # Reuse model name

        inhouse_base_valid = os.path.isdir(INHOUSE_PRINTING_PATH) if INHOUSE_PRINTING_PATH else False
        if not inhouse_base_valid: st.error(f"InHouse Printing path invalid: {INHOUSE_PRINTING_PATH}"); return
        if copy_mode == 'Into a New Subfolder' and not is_valid_foldername(subfolder_name): st.error(f"Invalid subfolder name."); return

        copied_stl_count = 0; error_count = 0
        total_stl_to_copy = len(source_file_paths)
        if total_stl_to_copy == 0: st.warning("No files found to copy."); return

        progress_bar = st.progress(0); status_text = st.empty()
        final_status_placeholder = st.empty() # Create placeholder for final message
        status_text.text("Starting STL file copy..."); final_destination_paths_used = set()

        if copy_mode == 'Into a New Subfolder': target_dir = os.path.join(INHOUSE_PRINTING_PATH, subfolder_name)
        else: target_dir = INHOUSE_PRINTING_PATH

        try:
            os.makedirs(target_dir, exist_ok=True)
            final_destination_paths_used.add(target_dir)
        except OSError as e: st.error(f"Error creating destination '{target_dir}': {e}"); return

        #current_copied_count = 0 # Use current_copied_count locally
        for i, source_file_path in enumerate(source_file_paths):
            file = os.path.basename(source_file_path)
            destination_file_path = os.path.join(target_dir, file) # Original filename
            status_text.text(f"Copying: {file} ({i+1}/{total_stl_to_copy})") # Update progress text
            try:
                shutil.copy2(source_file_path, destination_file_path)
                current_copied_count += 1
            except (shutil.Error, OSError, Exception) as e: st.error(f"Error copying '{file}' to '{target_dir}': {e}"); error_count += 1
            finally: progress_bar.progress((i + 1) / total_stl_to_copy)

    # --- Common Completion Logic (MODIFIED - Using Placeholder Explicitly) ---
    if 'scan_status' in locals(): scan_status.empty() # Clear scan message
    status_text.empty() # Clear the "Copying..." message
    final_status_placeholder.empty() # Explicitly clear placeholder before writing final status

    # Use the placeholder to display the single, correct final message
    # Use current_copied_count which was updated in the loops
    if current_copied_count > 0:
        final_status_placeholder.success(f"Successfully copied {current_copied_count} '.stl' file(s) to designated location(s).")
        # Optionally, still mention errors if they occurred alongside success
        if error_count > 0:
             st.warning(f"Note: Encountered {error_count} error(s) during the process (see details above).")
    elif error_count > 0: # No files copied (or copy incomplete) AND errors occurred
        final_status_placeholder.error(f"Copy failed. Encountered {error_count} error(s).")
    elif total_stl_to_copy > 0: # No files copied, no errors, but files were expected
         final_status_placeholder.warning("Attempted copy, but no files matching criteria were transferred (check filters/permissions).")
    # No message needed if total_stl_to_copy was 0 (handled by early return)


    # Open destination logic (remains the same)
    if open_destination and current_copied_count > 0 and error_count == 0:
        st.write("Opening destination folder(s)...")
        for dest_path in final_destination_paths_used: open_folder_in_explorer(dest_path)
    elif open_destination and error_count > 0:
        st.warning("Destination(s) not opened due to errors.")
    elif open_destination and current_copied_count == 0:
         st.warning("Destination(s) not opened as no files copied.")
# --- End MODIFIED copy_items function ---


def open_folder_in_explorer(folder_path):
    """Opens a folder in the system's file explorer."""
    try:
        norm_path = os.path.normpath(folder_path)
        if platform.system() == "Windows": os.startfile(norm_path)
        elif platform.system() == "Darwin": subprocess.Popen(["open", norm_path])
        elif platform.system() == "Linux": subprocess.Popen(["xdg-open", norm_path])
        else: st.warning(f"Unsupported OS: {platform.system()}.")
    except Exception as e: st.error(f"Error opening folder '{folder_path}': {e}")

def is_valid_foldername(foldername):
    """Checks for invalid characters in a potential folder name."""
    if not foldername: return False
    if re.search(r'[<>:"/\\|?*\x00-\x1F]', foldername): return False
    reserved = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
    if foldername.upper().split('.')[0] in reserved: return False
    if foldername.endswith(('.', ' ')): return False
    return True

def format_size(size_bytes):
   """Converts bytes to human-readable format."""
   if size_bytes == 0: return "0 B"
   size_name = ("B", "KB", "MB", "GB", "TB")
   i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2) if p > 0 else 0
   return f"{s} {size_name[i]}"

# --- Initialize Default State ---
default_state = {
    'search_terms': "", 'selected_folder_paths': {}, 'selected_items_to_copy': None,
    'selected_search_paths': [], 'last_search_terms': [], 'found_folders_cache': {},
    'model_copy_mode': 'Directly into Base', 'model_new_folder_name': '',
    'tissue_copy_mode': 'Directly into Base', 'tissue_new_folder_name': '',
    'tissue_files_found_in_selection': False,
    'last_selected_paths_for_items': {}, 'empty_selected_folders_list': [],
    'selected_display_names': [],
    'total_copy_selected_size': 0, 'display_model_selected_size': 0,
    'non_stl_in_selection': False, 'app_just_reset': False,
    'search_mode': 'folder', 'found_file_paths': [],
}

# --- Reset Function ---
def reset_app_state():
    """Clears relevant session state variables and sets reset flag."""
    keys_to_clear = list(default_state.keys())
    keys_to_clear.remove('app_just_reset')
    for key in keys_to_clear:
        if key in default_state: st.session_state[key] = default_state[key]
    st.session_state['app_just_reset'] = True

# --- Streamlit App ---
st.set_page_config(layout="wide")

# Initialize state
for key, value in default_state.items():
    if key not in st.session_state: st.session_state[key] = value

# --- Title ---
st.title("📁 Folder/File Search & STL Copy App")
st.write("Search folders OR recursively search files in 'InHouse Printing' and copy specific `.stl` files.")

# --- Custom CSS ---
st.markdown("""<style>.stMultiSelect [data-baseweb="select"] li[aria-selected="true"] {background-color: #add8e6 !important; color: black !important;}</style>""", unsafe_allow_html=True)


# --- UI Sections ---

# 1. Select Search Locations
st.subheader("1. Select Search Locations")
selected_search_paths_on_load = []
num_paths = len(PREDEFINED_PATHS)
cols_per_row = min(num_paths, 4)
num_rows = (num_paths + cols_per_row - 1) // cols_per_row
path_items = list(PREDEFINED_PATHS.items())
item_index = 0
app_was_reset = st.session_state.get('app_just_reset', False)
for r in range(num_rows):
    cols = st.columns(cols_per_row)
    for c in range(cols_per_row):
        if item_index < num_paths:
            path_name, path = path_items[item_index]
            is_valid = os.path.isdir(path) if path else False
            label = f"{path_name}"; tooltip = f"Path: {path}" if is_valid else f"Invalid Path: {path}"
            checkbox_key = f"checkbox_{path_name}"
            # Default check ONLY Model Material if valid
            default_checked = (path_name == "Model Material" and is_valid)
            if app_was_reset: st.session_state[checkbox_key] = default_checked
            elif checkbox_key not in st.session_state: st.session_state[checkbox_key] = default_checked
            is_selected = cols[c].checkbox(label, value=st.session_state[checkbox_key], key=checkbox_key, disabled=not is_valid, help=tooltip)
            if is_selected and is_valid: selected_search_paths_on_load.append(path)
            item_index += 1
if app_was_reset: st.session_state['app_just_reset'] = False # Clear flag

# --- Determine Search Mode ---
current_search_mode = 'folder' # Default
mixed_selection = False
if INHOUSE_PRINTING_PATH in selected_search_paths_on_load:
    if len(selected_search_paths_on_load) == 1:
        current_search_mode = 'file'
    else:
        mixed_selection = True # Contains InHouse Printing AND others

# Update state only if selection actually changed
if selected_search_paths_on_load != st.session_state.get('selected_search_paths'):
    st.session_state['selected_search_paths'] = selected_search_paths_on_load
    st.session_state['search_mode'] = current_search_mode # Store the mode
    # Clear all downstream results when search locations change
    st.session_state['found_folders_cache'] = {}; st.session_state['found_file_paths'] = []
    st.session_state['selected_display_names'] = []; st.session_state['selected_folder_paths'] = {}
    st.session_state['selected_items_to_copy'] = None; st.session_state['last_selected_paths_for_items'] = {}
    st.session_state['empty_selected_folders_list'] = []; st.session_state['total_copy_selected_size'] = 0
    st.session_state['display_model_selected_size'] = 0; st.session_state['non_stl_in_selection'] = False
    st.session_state['tissue_files_found_in_selection'] = False
    st.rerun()
else:
    # Ensure search mode state is consistent even if paths didn't change
    st.session_state['search_mode'] = current_search_mode


# 2. Enter Search Terms
st.subheader("2. Enter Folder or File Name Search Terms")
search_terms_input = st.text_area(
    "Enter terms (one per line):",
    value=st.session_state['search_terms'], height=100,
    placeholder="e.g. 2025-12345 or modelbase",
    key="search_terms_widget"
)
if search_terms_input != st.session_state.get('search_terms'):
    st.session_state['search_terms'] = search_terms_input
    st.session_state['found_folders_cache'] = {}; st.session_state['found_file_paths'] = []
    st.session_state['selected_display_names'] = []; st.session_state['selected_folder_paths'] = {}
    st.session_state['selected_items_to_copy'] = None; st.session_state['last_selected_paths_for_items'] = {}
    st.session_state['empty_selected_folders_list'] = []; st.session_state['total_copy_selected_size'] = 0
    st.session_state['display_model_selected_size'] = 0; st.session_state['non_stl_in_selection'] = False
    st.session_state['tissue_files_found_in_selection'] = False
    st.rerun()
search_terms = [term.strip() for term in st.session_state['search_terms'].strip().split('\n') if term.strip()]

# 3. Perform Search and Display Results
st.subheader("3. Search Results & Selection")
not_found_terms = []

if mixed_selection:
    st.error("❌ Mixed Mode Error: Please select EITHER 'InHouse Printing' OR other locations, not both.")
    st.session_state['selected_items_to_copy'] = None
    st.session_state['found_folders_cache'] = {}; st.session_state['found_file_paths'] = []
elif not st.session_state.get('selected_search_paths'): st.warning("⚠️ Select search location(s).")
elif not search_terms: st.info("ℹ️ Enter search term(s).")
else:
    active_search_mode = st.session_state.get('search_mode', 'folder')

    # --- FILE SEARCH MODE ---
    if active_search_mode == 'file':
        st.write(f"**Mode:** Searching Files Recursively in `{INHOUSE_PRINTING_PATH}`")
        if search_terms != st.session_state.get('last_search_terms', []) or not isinstance(st.session_state.get('last_selected_paths_for_items'), list):
             with st.spinner(f"Searching files for: {', '.join(search_terms)}..."):
                 found_files = search_files_recursively(INHOUSE_PRINTING_PATH, search_terms)
                 st.session_state['found_file_paths'] = found_files
                 st.session_state['last_search_terms'] = search_terms
                 st.session_state['last_selected_paths_for_items'] = [] # Mark analysis needed
                 st.rerun()

        found_file_paths = st.session_state.get('found_file_paths', [])
        if found_file_paths:
            st.success(f"✅ Found {len(found_file_paths)} matching STL file(s).")
            with st.expander("Show Found Files (first 20)"):
                for fpath in found_file_paths[:20]: st.code(os.path.basename(fpath))
            # Analyze found files
            if found_file_paths != st.session_state.get('last_selected_paths_for_items', []):
                 st.info("Calculating size & checking types...")
                 with st.spinner("Analyzing found files..."):
                     items, total_copy_size, display_model_size, non_stl, tissue_found, _ = get_file_details(found_file_paths)
                     st.session_state['selected_items_to_copy'] = items
                     st.session_state['total_copy_selected_size'] = total_copy_size
                     st.session_state['display_model_selected_size'] = display_model_size
                     st.session_state['non_stl_in_selection'] = non_stl
                     st.session_state['tissue_files_found_in_selection'] = tissue_found
                     st.session_state['empty_selected_folders_list'] = []
                     st.session_state['last_selected_paths_for_items'] = found_file_paths
                     st.rerun()
        elif st.session_state.get('last_search_terms') == search_terms:
            st.info("ℹ️ No matching STL files found in the InHouse Printing path.")
            st.session_state['selected_items_to_copy'] = None; st.session_state['total_copy_selected_size'] = 0
            st.session_state['display_model_selected_size'] = 0; st.session_state['non_stl_in_selection'] = False
            st.session_state['tissue_files_found_in_selection'] = False; st.session_state['last_selected_paths_for_items'] = []

    # --- FOLDER SEARCH MODE ---
    elif active_search_mode == 'folder':
        st.write(f"**Mode:** Searching Top-Level Folders")
        search_terms_set = set(search_terms); last_search_terms_set = set(st.session_state.get('last_search_terms', []))
        selected_paths_set = set(st.session_state['selected_search_paths']); last_selected_paths_set = set(st.session_state.get('last_selected_paths', []))
        needs_search = (search_terms_set != last_search_terms_set or selected_paths_set != last_selected_paths_set)
        if needs_search:
            with st.spinner(f"Searching folders..."):
                all_found_folders_dict = {}
                for root_dir in st.session_state['selected_search_paths']:
                    origin_label = next((name for name, path in PREDEFINED_PATHS.items() if path == root_dir), "Unknown")
                    for search_term in search_terms:
                        found_in_root = search_top_level_folders(root_dir, search_term)
                        for folder_name, folder_path in found_in_root:
                            if folder_path not in all_found_folders_dict: all_found_folders_dict[folder_path] = (folder_name, origin_label)
                st.session_state['found_folders_cache'] = all_found_folders_dict
                st.session_state['last_search_terms'] = search_terms
                st.session_state['last_selected_paths'] = st.session_state['selected_search_paths']
                # Update display options based on newly found folders
                display_options_update = {f"{name}  (in ...{os.path.basename(os.path.dirname(path))})": path for path, (name, origin) in all_found_folders_dict.items()}
                st.session_state['selected_display_names'] = list(display_options_update.keys()) # Should this auto-select all found? Or clear selection? Currently sets options, not selection.
                st.session_state['selected_folder_paths'] = {} # Clear previous selection details
                st.session_state['selected_items_to_copy'] = None
                st.session_state['last_selected_paths_for_items'] = {} # Reset analysis trigger
                st.session_state['empty_selected_folders_list'] = []
                st.session_state['total_copy_selected_size'] = 0; st.session_state['display_model_selected_size'] = 0
                st.session_state['non_stl_in_selection'] = False; st.session_state['tissue_files_found_in_selection'] = False
                st.rerun()


        found_folders_map = st.session_state['found_folders_cache']
        if found_folders_map:
            display_options = {f"{name}  (in ...{os.path.basename(os.path.dirname(path))})": path for path, (name, origin) in found_folders_map.items()}
            sorted_display_names = sorted(display_options.keys())

            # Maintain previous selection if options are still valid, otherwise use default (which might be empty or based on needs_search logic)
            current_selection_display_raw = st.session_state.get('selected_display_names', [])
            # Filter selection to only include currently available options
            current_selection_display_filtered = [name for name in current_selection_display_raw if name in display_options]

            selected_display_names = st.multiselect(
                "Select folders to scan for STL files:",
                options=sorted_display_names,
                default=current_selection_display_filtered, # Use the filtered list
                key="folder_multiselect"
            )

            # Check if the multiselect widget's state has changed from the filtered list used as default
            if selected_display_names != current_selection_display_filtered:
                 st.session_state['selected_display_names'] = selected_display_names # Store the actual new selection from the widget
                 new_selected_folder_paths = {display_options[name]: found_folders_map[display_options[name]][1] for name in selected_display_names}
                 st.session_state['selected_folder_paths'] = new_selected_folder_paths
                 st.session_state['last_selected_paths_for_items'] = {} # Mark for re-calculation
                 st.rerun()
            else:
                # If selection hasn't changed via widget, ensure internal state reflects the current filtered selection
                new_selected_folder_paths = {display_options[name]: found_folders_map[display_options[name]][1] for name in selected_display_names}
                if new_selected_folder_paths != st.session_state.get('selected_folder_paths'):
                     st.session_state['selected_folder_paths'] = new_selected_folder_paths
                     # Potentially trigger rerun if the dictionary content changed even if display names didn't (less likely but possible)


        current_selected_paths_dict = st.session_state.get('selected_folder_paths', {})
        last_selected_paths_for_items_dict = st.session_state.get('last_selected_paths_for_items', {})
        if current_selected_paths_dict != last_selected_paths_for_items_dict:
            if current_selected_paths_dict:
                st.info("Calculating size & checking types...")
                with st.spinner("Analyzing contents..."):
                    items_list, total_copy_size, display_model_size, non_stl, tissue_found, empty_list = get_recursive_folder_details(current_selected_paths_dict)
                    st.session_state['selected_items_to_copy'] = current_selected_paths_dict
                    st.session_state['total_copy_selected_size'] = total_copy_size
                    st.session_state['display_model_selected_size'] = display_model_size
                    st.session_state['non_stl_in_selection'] = non_stl
                    st.session_state['tissue_files_found_in_selection'] = tissue_found
                    st.session_state['empty_selected_folders_list'] = empty_list
                    st.session_state['last_selected_paths_for_items'] = current_selected_paths_dict
                    st.rerun()
            else:
                 # Clear analysis results if selection becomes empty
                 st.session_state['selected_items_to_copy'] = None; st.session_state['total_copy_selected_size'] = 0
                 st.session_state['display_model_selected_size'] = 0
                 st.session_state['non_stl_in_selection'] = False; st.session_state['empty_selected_folders_list'] = []
                 st.session_state['last_selected_paths_for_items'] = {}; st.session_state['tissue_files_found_in_selection'] = False
                 # Do not rerun here unless explicitly needed, avoid potential loop if clearing state triggers this block again

        # Calculate not found terms after search and selection logic
        if search_terms and found_folders_map is not None: # Check found_folders_map exists
            all_search_terms_lower_set = set(term.lower() for term in search_terms)
            found_folder_names_lower_set = set(name.lower() for name, origin in found_folders_map.values())
            # Check if any part of a found folder name contains the search term
            current_not_found = [
                term for term in search_terms
                if not any(term.lower() in name_lower for name_lower in found_folder_names_lower_set)
            ]
            not_found_terms = sorted(list(set(current_not_found)))


# --- Sidebar Status Display ---
with st.sidebar:
    st.markdown("---"); st.subheader("Search Status")
    active_mode_sb = st.session_state.get('search_mode', 'folder')
    found_folders_map_sb = st.session_state.get('found_folders_cache', {})
    found_files_sb = st.session_state.get('found_file_paths', [])
    selected_folders_dict_sb = st.session_state.get('selected_folder_paths', {})
    empty_selected_sb = st.session_state.get('empty_selected_folders_list', [])
    total_copy_size_sb = st.session_state.get('total_copy_selected_size', 0)
    display_model_size_sb = st.session_state.get('display_model_selected_size', 0)
    non_stl_sb = st.session_state.get('non_stl_in_selection', False)
    tissue_found_sb = st.session_state.get('tissue_files_found_in_selection', False)

    # Determine if analysis is complete based on mode
    if active_mode_sb == 'file':
        # Analysis is complete if files were found and the analysis step ran (last_selected_paths matches found_files)
        items_ready = bool(found_files_sb) and (found_files_sb == st.session_state.get('last_selected_paths_for_items', []))
    else: # folder mode
        # Analysis is complete if folders were selected and the analysis step ran (last_selected_paths matches selected_folders)
        items_ready = bool(selected_folders_dict_sb) and (selected_folders_dict_sb == st.session_state.get('last_selected_paths_for_items', {}))


    has_results = bool(found_folders_map_sb) or bool(found_files_sb)
    search_attempted = bool(st.session_state.get('last_search_terms')) # Check if a search was actually run

    if not st.session_state.get('selected_search_paths'):
        st.sidebar.warning("Select search location(s).")
    elif not st.session_state.get('search_terms'):
        st.sidebar.info("Enter search term(s).")
    elif not has_results and search_attempted:
        st.sidebar.info("No matching items found.")
    elif not has_results and not search_attempted:
         st.sidebar.info("Perform a search.") # Or waiting for search


    # Display results count based on mode if results exist
    if active_mode_sb == 'file' and found_files_sb: st.sidebar.success(f"✅ Found {len(found_files_sb)} matching file(s).")
    elif active_mode_sb == 'folder' and found_folders_map_sb: st.sidebar.success(f"✅ Found {len(found_folders_map_sb)} matching folder(s).")

    # Display analysis details if items were selected/found and analysis is ready
    if items_ready and ( (active_mode_sb == 'file' and found_files_sb) or (active_mode_sb == 'folder' and selected_folders_dict_sb) ):
        st.sidebar.info(f"📊 Model Files Size (Display): **{format_size(display_model_size_sb)}**")
        if total_copy_size_sb > SIZE_LIMIT_BYTES:
            st.sidebar.warning(f"⚠️ Total Copy Size ({format_size(total_copy_size_sb)}) > {SIZE_LIMIT_MB:.0f} MB!")
        else:
             st.sidebar.info(f"Total Copy Size: {format_size(total_copy_size_sb)}") # Show size even if not over limit

        if non_stl_sb: st.sidebar.warning("⚠️ Selection includes non-STL files (won't be copied).")
        if tissue_found_sb: st.sidebar.info("ℹ️ Selection includes Tissue/Gingiva files.")
    elif (active_mode_sb == 'file' and found_files_sb and not items_ready) or \
         (active_mode_sb == 'folder' and selected_folders_dict_sb and not items_ready):
        st.sidebar.info("⏳ Analyzing selection...") # Indicate analysis is pending/running


    # --- Explicitly Separated Notifications ---
    # Show 'not found' only if a search was attempted for those terms in folder mode
    if active_mode_sb == 'folder' and not_found_terms and search_attempted:
        st.sidebar.markdown("**Folders not found for search term(s):**")
        for term in not_found_terms: st.sidebar.markdown(f"- `{term}`")
        st.sidebar.markdown("---")
    # Show 'empty/inaccessible' only if folders were selected and found to be empty/bad in folder mode
    if active_mode_sb == 'folder' and empty_selected_sb:
        empty_list_message = ["**Selected folders empty or inaccessible:**"]
        empty_list_message.extend([f"- `{os.path.basename(fp)}`" for fp in empty_selected_sb])
        st.sidebar.warning("\n".join(empty_list_message))
    # --- End Separated Notifications ---

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Reset Search"): reset_app_state(); st.rerun()

# 4. Select Destination and Copy Items
st.subheader("4. Select Destination & Copy STL Files")
active_search_mode_copy = st.session_state.get('search_mode', 'folder')

# Determine items to process based on mode and ensure analysis is complete
analysis_complete = False
items_to_process = None
if active_search_mode_copy == 'file':
    found_files = st.session_state.get('found_file_paths', [])
    if found_files and found_files == st.session_state.get('last_selected_paths_for_items', []):
        items_to_process = found_files
        analysis_complete = True
else: # folder mode
    selected_folders = st.session_state.get('selected_folder_paths', {})
    if selected_folders and selected_folders == st.session_state.get('last_selected_paths_for_items', {}):
        items_to_process = st.session_state.get('selected_items_to_copy', {}) # Should match selected_folders if analysis done
        analysis_complete = True


can_show_copy_section = bool(items_to_process) and analysis_complete
tissue_files_found = st.session_state.get('tissue_files_found_in_selection', False)

if can_show_copy_section:

    # --- Destination Controls ---
    if active_search_mode_copy == 'file':
        # Simplified controls for file mode (copying back to InHouse Printing)
        st.markdown(f"**Destination Base:** `{INHOUSE_PRINTING_PATH}`")
        mode_options = ('Directly into Base Path', 'Into a New Subfolder in Base Path')
        current_mode_internal = st.session_state.get('model_copy_mode', 'Directly into Base') # Reuse model state
        default_index = 0 if current_mode_internal == 'Directly into Base' else 1
        copy_mode_selection = st.radio("Copy structure:", mode_options, index=default_index, key='inhouse_copy_mode_radio', horizontal=True)
        selected_mode_internal = 'Directly into Base' if copy_mode_selection == mode_options[0] else 'Into a New Subfolder'
        if selected_mode_internal != current_mode_internal: st.session_state['model_copy_mode'] = selected_mode_internal; st.rerun()

        new_folder_name_valid = True
        if st.session_state['model_copy_mode'] == 'Into a New Subfolder':
            folder_input = st.text_input("Enter name for New Subfolder:", value=st.session_state.get('model_new_folder_name', ''), key='inhouse_new_folder_widget', placeholder="e.g., Copied_Files")
            # Update state immediately on input change for validation feedback
            if folder_input != st.session_state.get('model_new_folder_name'):
                st.session_state['model_new_folder_name'] = folder_input
                st.rerun() # Rerun to re-evaluate validity

            current_folder_name = st.session_state.get('model_new_folder_name', '').strip()
            if not current_folder_name: st.warning("Please enter subfolder name."); new_folder_name_valid = False
            elif not is_valid_foldername(current_folder_name): st.error("Invalid subfolder name."); new_folder_name_valid = False
            else: st.info(f"Subfolder: `{current_folder_name}`")

        # Disable button logic for file mode
        disable_copy_button = False
        base_path_valid = os.path.isdir(INHOUSE_PRINTING_PATH) if INHOUSE_PRINTING_PATH else False
        if not base_path_valid: disable_copy_button = True; st.error("Copying disabled: InHouse Printing path invalid.")
        elif st.session_state['model_copy_mode'] == 'Into a New Subfolder' and not new_folder_name_valid: disable_copy_button = True
        if st.session_state.get('total_copy_selected_size', 0) > SIZE_LIMIT_BYTES: disable_copy_button = True; st.error(f"Copying disabled: Total Copy Size > {SIZE_LIMIT_MB:.0f} MB.")
        if not items_to_process: disable_copy_button = True # Disable if list is empty (redundant with can_show_copy_section but safe)

    else: # Folder Mode Controls
        # --- Model Destination Controls ---
        st.markdown(f"**Model Folder Destination:** `{MODEL_BASE_PATH}`")
        model_mode_options = ('Directly into Model Base', 'Into a New Subfolder in Model Base')
        model_current_mode_internal = st.session_state.get('model_copy_mode', 'Directly into Base')
        model_default_index = 0 if model_current_mode_internal == 'Directly into Base' else 1
        model_copy_mode_selection = st.radio("Model file structure:", model_mode_options, index=model_default_index, key='model_copy_mode_radio', horizontal=True)
        model_selected_mode_internal = 'Directly into Base' if model_copy_mode_selection == model_mode_options[0] else 'Into a New Subfolder'
        if model_selected_mode_internal != model_current_mode_internal: st.session_state['model_copy_mode'] = model_selected_mode_internal; st.rerun()

        model_new_folder_name_valid = True
        if st.session_state['model_copy_mode'] == 'Into a New Subfolder':
            model_folder_input = st.text_input("Enter name for New Model Subfolder:", value=st.session_state.get('model_new_folder_name', ''), key='model_new_folder_widget', placeholder="e.g., Project_Models")
            # Update state immediately on input change
            if model_folder_input != st.session_state.get('model_new_folder_name'):
                st.session_state['model_new_folder_name'] = model_folder_input
                st.rerun() # Rerun to re-evaluate validity

            current_model_folder_name = st.session_state.get('model_new_folder_name', '').strip()
            if not current_model_folder_name: st.warning("Please enter Model subfolder name."); model_new_folder_name_valid = False
            elif not is_valid_foldername(current_model_folder_name): st.error("Invalid Model subfolder name."); model_new_folder_name_valid = False
            else: st.info(f"Model Subfolder: `{current_model_folder_name}`")

        # --- Tissue Destination Controls (Conditional) ---
        tissue_new_folder_name_valid = True
        if tissue_files_found:
            st.markdown("---"); st.markdown(f"**Tissue/Gingiva Destination:** `{TISSUE_BASE_PATH}`")
            tissue_mode_options = ('Directly into Tissue Base', 'Into a New Subfolder in Tissue Base')
            tissue_current_mode_internal = st.session_state.get('tissue_copy_mode', 'Directly into Base')
            tissue_default_index = 0 if tissue_current_mode_internal == 'Directly into Base' else 1
            tissue_copy_mode_selection = st.radio("Tissue/Gingiva file structure:", tissue_mode_options, index=tissue_default_index, key='tissue_copy_mode_radio', horizontal=True)
            tissue_selected_mode_internal = 'Directly into Base' if tissue_copy_mode_selection == tissue_mode_options[0] else 'Into a New Subfolder'
            if tissue_selected_mode_internal != tissue_current_mode_internal: st.session_state['tissue_copy_mode'] = tissue_selected_mode_internal; st.rerun()

            if st.session_state['tissue_copy_mode'] == 'Into a New Subfolder':
                tissue_folder_input = st.text_input("Enter name for New Tissue Subfolder:", value=st.session_state.get('tissue_new_folder_name', ''), key='tissue_new_folder_widget', placeholder="e.g., Project_Tissue")
                # Update state immediately on input change
                if tissue_folder_input != st.session_state.get('tissue_new_folder_name'):
                    st.session_state['tissue_new_folder_name'] = tissue_folder_input
                    st.rerun() # Rerun to re-evaluate validity

                current_tissue_folder_name = st.session_state.get('tissue_new_folder_name', '').strip()
                if not current_tissue_folder_name: st.warning("Please enter Tissue subfolder name."); tissue_new_folder_name_valid = False
                elif not is_valid_foldername(current_tissue_folder_name): st.error("Invalid Tissue subfolder name."); tissue_new_folder_name_valid = False
                else: st.info(f"Tissue Subfolder: `{current_tissue_folder_name}`")
            st.markdown("---")

        # --- Button Disablement Logic (Folder Mode) ---
        disable_copy_button = False
        model_base_valid = os.path.isdir(MODEL_BASE_PATH)
        tissue_base_valid = os.path.isdir(TISSUE_BASE_PATH) if tissue_files_found else True # Assume valid if no tissue found

        # Check base paths first
        if not model_base_valid: disable_copy_button = True; st.error("Copying disabled: Model Folder Destination invalid.")
        if tissue_files_found and not tissue_base_valid: disable_copy_button = True; st.error("Copying disabled: Tissue Destination invalid.")

        # Check subfolder names only if respective mode is selected and base path is valid
        if not disable_copy_button:
            if st.session_state['model_copy_mode'] == 'Into a New Subfolder' and not model_new_folder_name_valid: disable_copy_button = True
            if tissue_files_found and st.session_state['tissue_copy_mode'] == 'Into a New Subfolder' and not tissue_new_folder_name_valid: disable_copy_button = True

        # Check size limit and if items exist (last checks)
        if not disable_copy_button:
             if not items_to_process: disable_copy_button = True; st.info("No source folders identified for copying.") # Should not happen if can_show_copy_section is true
             if st.session_state.get('total_copy_selected_size', 0) > SIZE_LIMIT_BYTES: disable_copy_button = True; st.error(f"Copying disabled: Total Copy Size > {SIZE_LIMIT_MB:.0f} MB.")


    # --- Common Copy Button Area ---
    col1, col2 = st.columns([3, 1])
    open_dest_after_copy = col1.checkbox("Open destination folder(s) after successful copy?", value=False, key="open_dest_cb")
    copy_button_pressed = col2.button("🚀 Copy STL Files", type="primary", disabled=disable_copy_button)

    if copy_button_pressed and not disable_copy_button:
        copy_items(
            items_to_process=items_to_process,
            search_mode=active_search_mode_copy, # Pass the detected mode
            open_destination=open_dest_after_copy
        )

# Conditional messages if copy section isn't shown but search might have occurred
elif search_attempted: # Check if a search was actually run
    if active_search_mode_copy == 'folder' and not st.session_state.get('selected_folder_paths'):
         st.info("ℹ️ Select found folders in Step 3 to prepare for copying.")
    elif not analysis_complete and (st.session_state.get('found_file_paths') or st.session_state.get('selected_folder_paths')):
         st.info("⏳ Please wait for analysis to complete.")
    elif not items_to_process and analysis_complete: # Analysis done, but nothing qualified
         st.info("ℹ️ No items available to copy based on current selection and filters (e.g., only non-STLs found, or Exocad files filtered out).")
    # If no results were found initially, the message in the sidebar handles it.


# --- Footer ---
st.markdown("---")
st.write("Happy Batch Printing B!tch 😉") # footer

