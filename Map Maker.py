import os
import math
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import folium
from folium.plugins import MarkerCluster
from collections import Counter
import webview
import threading

def get_gps_data(image_path):
    """Extract GPS data from an image."""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if not exif_data:
            return None
        
        gps_info = {}
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag)
            if tag_name == "GPSInfo":
                for gps_tag in value:
                    gps_name = GPSTAGS.get(gps_tag)
                    gps_info[gps_name] = value[gps_tag]
        
        if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
            lat = convert_to_degrees(gps_info["GPSLatitude"])
            if gps_info.get("GPSLatitudeRef") == "S":
                lat = -lat
            lon = convert_to_degrees(gps_info["GPSLongitude"])
            if gps_info.get("GPSLongitudeRef") == "W":
                lon = -lon
            return (lat, lon)
    except Exception as e:
        return None

def convert_to_degrees(value):
    """Convert GPS coordinates to degrees."""
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)

class GPSPhotoMapperApp:
    def __init__(self, master):
        self.master = master
        master.title("GPS Photo Mapper")
        master.geometry("600x500")

        # Create main frame
        self.main_frame = ttk.Frame(master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Folder selection
        self.folder_label = ttk.Label(self.main_frame, text="Selected Folder: None")
        self.folder_label.pack(pady=10)

        self.select_folder_btn = ttk.Button(self.main_frame, text="Select Folder", command=self.browse_directory)
        self.select_folder_btn.pack(pady=10)

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, 
                                            variable=self.progress_var, 
                                            maximum=100, 
                                            length=300)
        self.progress_bar.pack(pady=10)

        # Status label
        self.status_label = ttk.Label(self.main_frame, text="")
        self.status_label.pack(pady=10)

        # Create Map button
        self.create_map_btn = ttk.Button(self.main_frame, text="Create Map", 
                                         command=self.create_map, 
                                         state=tk.DISABLED)
        self.create_map_btn.pack(pady=10)

        # Slider for adjusting cluster radius
        self.density_slider_label = ttk.Label(self.main_frame, text="Cluster Density")
        self.density_slider_label.pack(pady=5)
        
        self.density_slider = ttk.Scale(self.main_frame, from_=1, to_=30, orient="horizontal", command=self.update_cluster_radius)
        self.density_slider.set(10)  # Default value for cluster radius
        self.density_slider.pack(pady=5)

        # Store selected folder and GPS data
        self.selected_folder = None
        self.gps_data = []
        self.cluster_radius = 10  # Default cluster radius

    def browse_directory(self):
        """Open a folder browser and update UI."""
        self.selected_folder = filedialog.askdirectory(title="Select a Folder with Photos")
        if self.selected_folder:
            self.folder_label.config(text=f"Selected Folder: {self.selected_folder}")
            self.create_map_btn.config(state=tk.NORMAL)
            # Reset previous state
            self.progress_var.set(0)
            self.status_label.config(text="")
            self.gps_data = []

    def scan_directory(self):
        """Scan a directory for images and extract GPS data."""
        gps_data = []
        count = 0
        total_files = sum(len(files) for _, _, files in os.walk(self.selected_folder))

        for root, _, files in os.walk(self.selected_folder):
            for idx, file in enumerate(files, start=1):
                if file.lower().endswith((".jpg", ".jpeg", ".png")):
                    file_path = os.path.join(root, file)
                    gps = get_gps_data(file_path)
                    if gps:
                        gps_data.append(gps)
                        count += 1

                # Update progress
                progress_percentage = (idx / total_files) * 100
                self.update_progress(progress_percentage, f"Scanning: {file} [{count} photos found]")

        return gps_data

    def update_progress(self, percentage, status_text):
        """Update progress bar and status label from a background thread."""
        self.progress_var.set(percentage)
        self.status_label.config(text=status_text)
        self.master.update_idletasks()

    def create_map(self):
        """Create a map with photo locations using persistent MarkerCluster style."""
        print("Creating map...")  # Debugging line
        # Start the scanning process in a separate thread
        threading.Thread(target=self.process_map_creation, daemon=True).start()

    def process_map_creation(self):
        """Process the map creation in the background."""
        # Scan for GPS data
        self.gps_data = self.scan_directory()

        if not self.gps_data:
            messagebox.showinfo("No GPS Data", "No GPS data found in the selected folder.")
            return

        # Sanitize the GPS data
        sanitized_data = [
            location for location in self.gps_data
            if isinstance(location, tuple) and len(location) == 2
            and all(isinstance(coord, (int, float)) and not math.isnan(coord) for coord in location)
        ]
        
        if not sanitized_data:
            messagebox.showinfo("No Valid Data", "No valid GPS data found.")
            return

        # Count occurrences of each location
        location_counts = Counter(sanitized_data)

        # Create a map centered at the first valid location
        map_center = list(location_counts.keys())[0]
        m = folium.Map(location=map_center, zoom_start=5)

        # Add a MarkerCluster layer with persistent cluster behavior
        marker_cluster = MarkerCluster(
            maxClusterRadius=self.cluster_radius  # Use the value from the slider
        ).add_to(m)

        # Add markers to the cluster
        for location, count in location_counts.items():
            folium.Marker(
                location=location,
                icon=folium.DivIcon(
                    html=f"""<div style="color: white; background: blue; border-radius: 50%; 
                             width: 20px; height: 20px; text-align: center; font-size: 10px;">
                             {count}</div>"""
                )
            ).add_to(marker_cluster)

        # Save the map to a temporary HTML file
        output_file = "temp_gps_map.html"
        m.save(output_file)

        # Update the UI to show the map creation process is finished
        self.master.after(0, self.open_map_in_webview, output_file)

    def open_map_in_webview(self, output_file):
        """Open the generated map in the WebView window."""
        # Open the map in a WebView window
        webview.create_window('GPS Photo Map', output_file)
        webview.start()

    def update_cluster_radius(self, value):
        """Update the cluster radius based on the slider value."""
        self.cluster_radius = int(float(value))
        print(f"Cluster radius updated: {self.cluster_radius}")

def main():
    # Create the main Tkinter window
    root = tk.Tk()
    
    # Create the application
    app = GPSPhotoMapperApp(root)
    
    # Start the Tkinter event loop
    root.mainloop()

if __name__ == "__main__":
    main()
