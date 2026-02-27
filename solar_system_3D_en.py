from ursina import *
from ursina.shaders import lit_with_shadows_shader
from ursina.prefabs.dropdown_menu import DropdownMenu, DropdownMenuButton
from ursina.prefabs.input_field import InputField
from ursina.prefabs.health_bar import HealthBar
from astropy.coordinates import get_body_barycentric, get_sun, get_body, SkyCoord, solar_system_ephemeris, EarthLocation, Angle, CartesianRepresentation
from astropy.time import Time, TimeDelta
from astropy.utils.iers import IERS_A_URL, IERS_A, IERS_B_URL, IERS_B
from astropy.utils.data import clear_download_cache, download_file
from astropy.utils import iers# pip install -- update astropy-iers-data
import astropy.units as u
from astral.sun import sun
from astral.moon import moonrise, moonset
from astral import LocationInfo
from scipy.signal import savgol_filter
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import ctypes
import win32con
import threading
import requests
from pathlib import Path
import numpy as np
import json
import sys
import gc
# solar_system_ephemeris requires jplephem installed
# Also pytest Has To Be Installed
# Important To Note That Ursina Y And Z Axis Are Reversed For Using Astropy. Y=Z, Z=Y
version="2026.02.25"
def show_message_box(title, style, message):
    MB_YESNO = 0x00000004  # Style for Yes and No buttons
    IDYES = 6              # Return value if Yes is clicked
    IDNO = 7               # Return value if No is clicked
    if style=="info":style = win32con.MB_OK | win32con.MB_ICONINFORMATION
    elif style=="warning":style = win32con.MB_OK | win32con.MB_ICONEXCLAMATION
    elif style=="error":style = win32con.MB_OK | win32con.MB_ICONHAND
    elif style=="question":style = MB_YESNO | win32con.MB_ICONQUESTION
    elif style=="retry":style=win32con.MB_ABORTRETRYIGNORE | win32con.MB_ICONHAND
    elif style=="asterisk":style=win32con.MB_ICONASTERISK
    ctypes.windll.user32.MessageBoxW(None, message,  title, style)
def download_iers_data():
    try:
        iers_a=Path("_internal/astropy_iers_data/data/finals2000A.all")
        iers_b=Path("_internal/astropy_iers_data/data/eopc04.1962-now")
        home_dir = os.path.dirname(sys.executable)
        IERS_A_Path=os.path.join(home_dir, iers_a)
        IERS_B_Path=os.path.join(home_dir, iers_b)
        path_list=[IERS_B_Path, IERS_A_Path]
        try:
            while not iers_stop:
                for item in enumerate(path_list):
                    if os.path.exists(item):os.remove(item)# Delete The Original iers file in astropy And ReCreate 
                    if item==IERS_A_Path:response = requests.get(IERS_A_URL, stream=True)
                    elif item==IERS_B_Path:response = requests.get(IERS_B_URL, stream=True)
                    else:break
                    response.raise_for_status()  # Raise an exception for bad status codes
                    with open(item, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    clear_download_cache()# Place The New Data Into Cache
                    if item==IERS_A_Path:
                        download_file(IERS_A_URL, cache='update', timeout=30, show_progress=False)
                        IERS_A.open()
                        iers_stop.set()
                    elif item==IERS_B_Path:
                        download_file(IERS_B_URL, cache='update', timeout=30, show_progress=False)
                        IERS_B.open()
                    else:break
                    msg1="IERS-A And IERS-B Files Have Been Sucessfully Updated!\n"
                    msg2="These Files Include Earth Orientation Parameters (EOP).\n"
                    msg3="Also Includes Daily Data For Polar Motion, Universal\n"
                    msg4="Time (UT1-UTC), And Celestial Pole Offsets."
                    msg=msg1+msg2+msg3+msg4
                    show_message_box("Download IERS Data", "info", msg)
                    return
            iers_thread.join(timeout=2.0)        
        except requests.exceptions.RequestException as e:
            msg=f"Error: {e}"
            show_message_box("Downloading IERS Data Failure", "error", msg)
            return
    except Exception as e:
        return f"Error: {e}"
def download_iers():
    try:
        if getattr(sys, 'frozen', False):
            requests.get("https://www.google.com", timeout=7)# Check Internet Connection
            global iers_stop
            iers_stop = threading.Event()
            global iers_thread
            iers_thread = threading.Thread(target=download_iers_data)
            iers_thread.daemon = True # Allows the application to close even if the thread is running
            iers_thread.start()
        else:return    
    except Exception as e:
        msg1="Maybe No Internet Connection!\n"
        msg2=f"Error: {e}"
        msg=msg1+msg2
        show_message_box("Download IERS Data", "error", msg)
def check_iers_age():
    dat = iers.earth_orientation_table.get()
    last_mjd = dat['MJD'][-1]
    last_date = Time(last_mjd, format='mjd', scale='utc')
    age = abs((Time.now() - last_date) + 365 * u.day)
    if age.value >= 15:
        MB_YESNO = 0x00000004  # Style for Yes and No buttons
        IDYES = 6              # Return value if Yes is clicked
        IDNO = 7               # Return value if No is clicked
        msg1="IERS-A And IERS-B Files Are Out Of Date!\n"
        msg2="These Files Include Earth Orientation Parameters (EOP).\n"
        msg3="Also Includes Daily Data For Polar Motion, Universal\n"
        msg4="Time (UT1-UTC), And Celestial Pole Offsets. To Update\n"
        msg5="Select Yes Or No To Update At A Later Time. This Update\n"
        msg6="May Take Some Time. You Will Be Notified When Completed!"
        msg=msg1+msg2+msg3+msg4+msg5+msg6
        response = ctypes.windll.user32.MessageBoxW(0, msg, "Download IERS Data", MB_YESNO)
        if response == IDYES:download_iers()
        elif response == IDNO:return
        else:return
check_iers_age()# Just incase auto-update isn't working
class Our_Solar_System(Entity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parent=camera.ui
        self.dt=0
        self.timer = 0
        self.delay_executed = False
        Text.size=0.015
        self.ignore_paused = True # Allow For Input While Paused
        self.planets = {}
        self.Planets_Data=[]# Referenced From Sun
        self.Real_Moon={}# Referenced From Earth
        self.Earth_Location=object
        self.Earth_Rotation=[]
        self.Sun_Near=10e15
        self.Sun_Near=10e15
        self.Moon_Near=10e15
        self.Mercury_Near=10e15
        self.Venus_Near=10e15
        self.Mars_Near=10e15
        self.Jupiter_Near=10e15
        self.Saturn_Near=10e15
        self.Uranus_Near=10e15
        self.Sun_RiseSet=[]
        self.last_sunrise=None
        self.Moon_RiseSet=[]
        self.last_moonrise=None
        self.New_Full_Moons=[]
        self.Moon_Illuminations=[]
        self.Moon_Phases=[]
        self.Moon_Date=None
        self.UTC_Time=[]
        self.Local_Time=()
        self.Scale_Factor = 4
        self.Time_Zone=object
        self.Data_Ready=False
        self.Old_Start_Time=""
        self.Old_Duration=None
        self.Old_Increment=None
        self.Old_Latitude=None
        self.Old_Longitude=None
        self.Old_Altitude=None
        self.Bar_value=0
        self.delay=0
        self.data_enabled = True
        pgm_path=Path(__file__).parent.absolute()
        de442_path=os.path.join(pgm_path,"de442.bsp")
        self.de442_divisor=149597870.691# AU Conversion
        self.ephemeris_path = os.path.expanduser(de442_path) # Replace with your actual path
        solar_system_ephemeris.set(self.ephemeris_path)
        self.repeat=True
        self.measurement_units="au"
        self.factor=1.0
        self.inputfields_enabled=True
        self.Time_Zone=None
        self.bar_stop_event = threading.Event()
        self.bar_thread_running=False
        self.bar_thread=None
        self.earth_pivot = Entity(name="earth_pivot", eternal=True)
        self.mars_pivot = Entity(name="mars_pivot", eternal=True)
        self.jupiter_pivot = Entity(name="jupiter_pivot", eternal=True)
        self.saturn_pivot = Entity(name="saturn_pivot", eternal=True)
        self.uranus_pivot = Entity(name="uranus_pivot", eternal=True)
        self.neptune_pivot = Entity(name="neptune_pivot", eternal=True)
        self.earth_pivot.rotation_z = 23.45# Axis Pivot
        self.mars_pivot.rotation_z = 25.19# Axis Pivot
        self.jupiter_pivot.rotation_z = 3.1
        self.saturn_pivot.rotation_z = 26.7
        self.uranus_pivot.rotation_z = 97.8
        self.neptune_pivot.rotation_z = 28.3
        self.sidereal_rotation = [0.2559727, 0.0617284, 15.04178, 1/365.256, 14.624238319, 36.302521, 33.644859814, 20.88974859, 22.345]
        self.space = Entity(name="space", model='cube', texture='stars', double_sided=True,  scale=(10000, -10000, 10000), eternal=True)
        self.sun_rotation=0.6122449# # Degrees/hr.
        self.sun = Entity(name="sun", model='sphere', color=color.yellow, unlit=True, scale=1.5, texture='sun', eternal=True)
        self.sun.enabled=False
        self.sunlight = PointLight(parent=self.sun, position=(0,0,0), color=color.white, eternal=True)
        self.ambient = AmbientLight(color=color.rgba(100, 100, 100, 0.5), eternal=True)
        x_line_points = [Vec3(-10000, 0, 0), Vec3(100000, 0, 0)]
        y_line_points = [Vec3(0, 0, -10000), Vec3(0, 0, 10000)]
        z_line_points = [Vec3(0, -10000, 0), Vec3(0, 10000, 0)]
        self.x_grid_line = Entity(model=Mesh(vertices=x_line_points, mode='line', thickness=1), double_sided=True, color=color.dark_gray, eternal=True)
        self.y_grid_line = Entity(model=Mesh(vertices=y_line_points, mode='line', thickness=1), double_sided=True, color=color.dark_gray, eternal=True)
        self.z_grid_line = Entity(model=Mesh(vertices=z_line_points, mode='line', thickness=1), double_sided=True, color=color.dark_gray, eternal=True)
        self.pause_handler = Entity(ignore_paused=True, eternal=True)        
        self.pause_menu = Entity(parent=self.parent, enabled=True, ignore_paused=True, eternal=True) # Initially hidden
        self.progress_bar = HealthBar(parent=self.parent, ignore_paused=True, bar_color=color.lime.tint(-.25), roundness=.5, value=0.0, max_value=100.00, scale=(1.0, .02), position=(-0.50, 0.4), eternal=True)
        self.progress_bar.text_entity.color = color.yellow
        self.pos_display = Text(parent=self.parent, text='', x=0.37, y=-0.47, scale=(1, 1), color=color.cyan, text_size=1.0, eternal=True)
        self.status = Text('PAUSED', origin=(0, -18.4), scale=1.5, parent=self.pause_menu, color=color.yellow, eternal=True)
        self.exit_button = Button(text='Quit', scale_x=0.08, scale_y=0.025, position=(0.84, 0.485), color=color.red, text_size=0.9, text_color=color.black, eternal=True)
        self.hide_data = Button(text='Hide Data', scale_x=0.12, scale_y=0.025, position=(0.73, 0.485), color=color.cyan, text_size=0.9, text_color=color.black, eternal=True)
        self.start_stop_button = Button(text='Start', scale_x=0.08, scale_y=0.025, position=(0.21, 0.485), color=color.cyan, text_size=0.9, text_color=color.black, eternal=True)
        self.grid = Button(text='Toggle Grid', scale_x=0.13, scale_y=0.025, position=(0.595, 0.485), color=color.cyan, text_size=0.9, text_color=color.black, eternal=True)
        self.repeat_button = Button(text='Repeat is On', scale_x=0.15, scale_y=0.025, position=(0.445, 0.485), color=color.cyan, text_size=0.9, text_color=color.black, eternal=True)
        self.units_menu=DropdownMenu('Select Units', buttons=[DropdownMenuButton(text='AU', on_click=Func(self.select_units, 'AU'),ignore_paused=True, eternal=True), 
                                        DropdownMenuButton(text='U.S.', on_click=Func(self.select_units, 'U.S.'),ignore_paused=True, eternal=True), 
                                        DropdownMenuButton(text='Metric', on_click=Func(self.select_units, 'Metric'), ignore_paused=True, eternal=True)],
                                        ignore_paused=True, scale=(0.10, 0.026), position=(0.26, 0.498), color=color.cyan, text_size=0.9, text_color=color.black, enabled = True, eternal=True)
        self.delay_lbl = Text(parent=self.parent, text="Delay in sec.", x=0.09, y=0.49, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.delay = InputField(parent=self.parent, x=0.09, y=0.475, scale=(0.1, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789.", eternal=True)
        self.increment_lbl = Text(parent=self.parent, text="Time Increment (hrs)", x=-0.06, y=0.49, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.increment = InputField(parent=self.parent, x=-0.06, y=0.475, scale=(0.15, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789.", eternal=True)
        self.increment_days_lbl = Text(parent=self.parent, text="Days =", x=-0.06, y=0.45, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.duration_lbl = Text(parent=self.parent, text="Time Duration (yrs)", x=-0.234, y=0.49, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.duration = InputField(parent=self.parent, x=-0.234, y=0.475, scale=(0.15, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789.", eternal=True)
        self.duration_days_lbl = Text(parent=self.parent, text="Days =", x=-0.234, y=0.45, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.start_time_lbl = Text(parent=self.parent, text="Local Start Date / Time", x=-0.445, y=0.49, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=0.8, eternal=True)
        self.start_time = InputField(parent=self.parent, x=-0.450, y=0.475, scale=(0.22, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789T-:", eternal=True)
        self.zone_lbl = Text(parent=self.parent, text="Local Time Zone", x=-0.73, y=0.49, scale=(1, 1), origin=(0, 0), color=color.cyan, text_size=1.0, eternal=True)
        self.time_zone_lbl = Button(text='None', scale_x=0.295, scale_y=0.025, position=(-0.72, 0.47), origin=(0, 0), color=color.lime, text_size=1.0, text_color=color.black, eternal=True) 
        self.latitude_lbl = Text(parent=self.parent, text="Latitude:", x=-0.79, y=0.44, scale=(1, 1), origin=(0.5, 0), color=color.cyan, text_size=1.0, eternal=True)
        self.latitude = InputField(parent=self.parent, x=-0.69, y=0.44, scale=(0.19, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789-.", eternal=True)
        self.longitude_lbl = Text(parent=self.parent, text="Longitude:", x=-0.79, y=0.417, scale=(1, 1), origin=(0.5, 0), color=color.cyan, text_size=1.0, eternal=True)
        self.longitude = InputField(parent=self.parent, x=-0.69, y=0.417, scale=(0.19, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789-.", eternal=True)
        self.altitude_lbl = Text(parent=self.parent, text="Altitude (m):", x=-0.79, y=0.394, scale=(1, 1), origin=(0.5, 0), color=color.cyan, text_size=1.0, eternal=True)
        self.altitude = InputField(parent=self.parent, x=-0.69, y=0.394, scale=(0.19, 0.02), origin=(0, 0.1), color="#1c0a47", text_size=0.0, limit_content_to="0123456789-.", eternal=True)
        self.time_now = Text(parent=self.parent, text="Local Time Now:", x=-0.88, y=0.371, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.time_end = Text(parent=self.parent, text="Local Time End:", x=-0.88, y=0.348, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.sun_rise_set = Text(parent=self.parent, text="Local Sunrise / Sunset:", x=-0.88, y=0.325, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.moon_rise_set = Text(parent=self.parent, text="Local Moonrise / Moonset:", x=-0.88, y=0.302, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.moon_new_full = Text(parent=self.parent, text="Next New Moon / Full Moon:", x=-0.88, y=0.279, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.moon_brightness = Text(parent=self.parent, text="Moon Illumination:", x=-0.88, y=0.256, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.earth_moon = Text(parent=self.parent, text="Moon Distance To Earth:", x=-0.88, y=0.233, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mercury_earth = Text(parent=self.parent, text="Mercury Distance To Earth:", x=-0.88, y=0.21, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.venus_earth = Text(parent=self.parent, text="Venus Distance To Earth:", x=-0.88, y=0.187, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mars_earth = Text(parent=self.parent, text="Mars Distance To Earth:", x=-0.88, y=0.164, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.jupiter_earth = Text(parent=self.parent, text="Jupiter Distance To Earth:", x=-0.88, y=0.141, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.saturn_earth = Text(parent=self.parent, text="Saturn Distance To Earth:", x=-0.88, y=0.118, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.uranus_earth = Text(parent=self.parent, text="Uranus Distance To Earth:", x=-0.88, y=0.095, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.neptune_earth = Text(parent=self.parent, text="Neptune Distance To Earth:", x=-0.88, y=0.072, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mercury_sun = Text(parent=self.parent, text="Mercury Distance To Sun:", x=-0.88, y=0.049, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.venus_sun = Text(parent=self.parent, text="Venus Distance To Sun:", x=-0.88, y=0.026, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.earth_sun = Text(parent=self.parent, text="Earth Distance To Sun:", x=-0.88, y=0.003, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mars_sun = Text(parent=self.parent, text="Mars Distance To Sun:", x=-0.88, y=-0.02, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.jupiter_sun = Text(parent=self.parent, text="Jupiter Distance To Sun:", x=-0.88, y=-0.043, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.saturn_sun = Text(parent=self.parent, text="Saturn Distance To Sun:", x=-0.88, y=-0.066, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.uranus_sun = Text(parent=self.parent, text="Uranus Distance To Sun:", x=-0.88, y=-0.089, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.neptune_sun = Text(parent=self.parent, text="Neptune Distance To Sun:", x=-0.88, y=-0.112, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.moon_orbits = Text(parent=self.parent, text="Moon Orbits Sun / Orbits Earth:", x=-0.88, y=-0.135, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mercury_days = Text(parent=self.parent, text="Mercury Rotations / Orbits:", x=-0.88, y=-0.158, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.venus_days = Text(parent=self.parent, text="Venus Rotations / Orbits:", x=-0.88, y=-0.181, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.earth_days = Text(parent=self.parent, text="Earth Rotations / Orbits:", x=-0.88, y=-0.204, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mars_days = Text(parent=self.parent, text="Mars Rotations / Orbits:", x=-0.88, y=-0.227, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.jupiter_days = Text(parent=self.parent, text="Jupiter Rotations / Orbits:", x=-0.88, y=-0.250, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.saturn_days = Text(parent=self.parent, text="Saturn Rotations / Orbits:", x=-0.88, y=-0.273, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.uranus_days = Text(parent=self.parent, text="Uranus Rotations / Orbits:", x=-0.88, y=-0.296, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.sun_nearest = Text(parent=self.parent, text="Sun Nearest To Earth Date / Distance:", x=-0.88, y=-0.319, scale=(1.1, 1.1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.moon_nearest = Text(parent=self.parent, text="Moon Nearest To Earth Date / Distance:", x=-0.88, y=-0.342, scale=(1.1, 1.1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mercury_nearest = Text(parent=self.parent, text="Mercury Nearest To Earth Date / Distance:", x=-0.88, y=-0.365, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.venus_nearest = Text(parent=self.parent, text="Venus Nearest To Earth Date / Distance::", x=-0.88, y=-0.388, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.mars_nearest = Text(parent=self.parent, text="Mars Nearest To Earth Date / Distance:", x=-0.88, y=-0.411, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.jupiter_nearest = Text(parent=self.parent, text="Jupiter Nearest To Earth Date / Distance:", x=-0.88, y=-0.434, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.saturn_nearest = Text(parent=self.parent, text="Saturn Nearest To Earth Date / Distance:", x=-0.88, y=-0.457, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        self.uranus_nearest = Text(parent=self.parent, text="Uranus Nearest To Earth Date / Distance:", x=-0.88, y=-0.480, scale=(1, 1), origin=(-.5, .5), color=color.cyan, text_size=1.0, eternal=True)
        # Default Values For Startup
        if not os.path.exists("Config.json"):
            with open("Config.json", "w") as json_file:# Create Empty json File
                    data={}
                    json.dump(data, json_file, indent=4) # indent=4 for pretty-printing
                    json_file.close()
            self.write_config()# Write Default Setup        
        else:
            self.read_config()# Retrieve Setup
        self.Increment_Days=float(self.increment.text) / 24# Days
        self.increment_days_lbl.text=(f'Days = {str(round(float(self.increment.text)/24,3))}')
        self.duration_days_lbl.text=(f'Days = {str(round(float(self.duration.text)*365.256,3))}')
        self.time_now.text=(f'Local Time Now: {self.start_time.text.replace('T','  Hrs: ')}')
        self.dt=0
        self.Earth_Location=EarthLocation.from_geodetic(lon=float(self.longitude.text) * u.deg, lat=float(self.latitude.text) * u.deg, height=float(self.altitude.text) * u.m)
        # Bindings
        self.increment.on_value_changed = lambda: self.validate_float_realtime(self.increment)
        self.duration.on_value_changed = lambda: self.validate_float_realtime(self.duration)
        self.grid.on_click = self.toggle_grid
        self.hide_data.on_click = self.toggle_data
        self.exit_button.on_click = self.exit
        self.repeat_button.on_click = self.toggle_repeat
        self.start_stop_button._on_click = lambda: self.toggle_run_pause("key", 'toggle')
        self.pause_handler.input = self.toggle_run_pause
        self.set_timezone()
        self.setup_solar_system()
        self.disable_buttons()
        self.disable_data()
        self.disable_inputfields()   
    def read_config(self):
        try:
            with open('Config.json', 'r') as json_file:
                data = json.load(json_file)
                json_file.close()
            for key, value in data.items():
                if key=="0":
                    self.start_time.text = value
                    self.Start_Time = Time(self.start_time.text)
                elif key=="1":self.latitude.text = value
                elif key=="2":self.longitude.text = value
                elif key=="3":self.altitude.text = value
                elif key=="4":self.duration.text = value
                elif key=="5":self.increment.text = value
                elif key=="6":self.delay.text = value
                else: break
        except Exception as e:
            pass
    def write_config(self):
        if self.start_time.text=="":
            self.Start_Time = Time(f"{Time.now().iso.split(' ')[0]} 00:00:00")
            self.start_time.text=str(self.Start_Time.isot)[:-4]
        if self.latitude.text=="": self.latitude.text = str(34.708997164) 
        if self.longitude.text=="": self.longitude.text = str(-86.737163718)
        if self.altitude.text=="": self.altitude.text = str(210.0)
        if self.duration.text=="": self.duration.text = str(0.082135)#years
        if self.increment.text=="": self.increment.text = str(4.0)#hrs
        if self.delay.text=="": self.delay.text = str(0.1)#sec.
        try:
            temp_dict={}
            sc=json.load(open("Config.json", "r"))
            json.dump(sc,open("Config.json", "w"),indent=4)
            temp_dict[0]=self.start_time.text
            temp_dict[1]=self.latitude.text
            temp_dict[2]=self.longitude.text
            temp_dict[3]=self.altitude.text
            temp_dict[4]=self.duration.text
            temp_dict[5]=self.increment.text
            temp_dict[6]=self.delay.text
            with open("Config.json", "w") as outfile:json.dump(temp_dict, outfile)
            outfile.close()
            temp_dict.clear()
        except Exception as e:
            pass
    def setup_solar_system(self):
        Text.size=0.015
        EditorCamera().enabled = True
        EditorCamera(rotation=(90, 0, 0))
        camera.world_position = Vec3(0, 20, 0)
        application.paused=True
        planet_radius=[0.1915, 0.475, 5.5, 0.1364, 0.266, 5.486, 4.57, 1.99, 1.932]# Radius Referenced to Earth Using Ratios. 6378.1 km = 0.5
        self.planets = {
                "mercury": Entity(name="mercury",model='sphere', color=color.white, scale=planet_radius[0], texture="mercury", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "venus": Entity(name="venus", model='sphere', color=color.white, scale=planet_radius[1], texture="venus", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "earth": Entity(name="earth", parent=self.earth_pivot, model='sphere', color=color.white, scale=planet_radius[2], rotation=(0,0,0), position=(0,0,0), texture="earth_night", shader=lit_with_shadows_shader),
                "moon": Entity(name="moon", parent=self.earth_pivot, model='sphere', color=color.white, scale=planet_radius[3], texture="moon", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "mars": Entity(name="mars", parent=self.mars_pivot, model='sphere', color=color.white, scale=planet_radius[4], texture="mars", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "jupiter": Entity(name="jupiter", parent=self.jupiter_pivot, model='sphere', color=color.white, scale=planet_radius[5], texture="jupiter", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "saturn": Entity(name="saturn", parent=self.saturn_pivot, model='sphere', color=color.white, scale=planet_radius[6], texture="saturn", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "uranus": Entity(name="uranus" ,parent=self.uranus_pivot,model='sphere', color=color.white, scale=planet_radius[7], texture="uranus", position=(-15,-15,-15), shader=lit_with_shadows_shader),
                "neptune": Entity(name="neptune", parent=self.neptune_pivot,model='sphere', color=color.white, scale=planet_radius[8], texture="neptune", position=(-15,-15,-15), shader=lit_with_shadows_shader)}
    def reset_solar_system(self):
        planet_names=["mercury", "venus", "earth", "moon", "mars", "jupiter", "saturn", "uranus", "neptune"]
        for name in planet_names:destroy(self.planets[name])
        self.dt=0
        self.planets = []
        self.Planets_Data=[]# Referenced From Sun
        self.Real_Moon={}# Referenced From Earth
        self.Earth_Rotation=[]
        self.Sun_RiseSet=[]
        self.last_sunrise=None
        self.Moon_RiseSet=[]
        self.last_moonrise=None
        self.New_Full_Moons=[]
        self.Moon_Illuminations=[]
        self.Moon_Phases=[]
        self.Moon_Date=None
        self.UTC_Time=[]
        self.Local_Time=()
        self.set_timezone()
        self.setup_solar_system()
    def exit(self):# Destroy all Entities Including eternal=True
        self.bar_stop_event.set()
        self.bar_thread_running=False
        self.write_config()
        application.quit()
        gc.collect()
        sys.exit()
    def toggle_grid(self):
        self.x_grid_line.enabled = not self.x_grid_line.enabled
        self.y_grid_line.enabled = not self.y_grid_line.enabled
        self.z_grid_line.enabled = not self.z_grid_line.enabled
        if self.x_grid_line.enabled == True:self.pos_display.enabled = True
        else:self.pos_display.enabled = False
    def select_units(self, txt):
        if txt=="AU":
            self.measurement_units = "au"
            self.factor=1.0
        elif txt=="Metric":
            self.measurement_units = "km"
            self.factor=149597870.691
        elif txt=="U.S.":
            self.measurement_units = "mi"
            self.factor=92955807.26743
        self.Sun_Near=10e15
        self.Sun_Near=10e15
        self.Moon_Near=10e15
        self.Mercury_Near=10e15
        self.Venus_Near=10e15
        self.Mars_Near=10e15
        self.Jupiter_Near=10e15
        self.Saturn_Near=10e15
        self.Uranus_Near=10e15
    def toggle_data(self):
        if self.hide_data.text == "Hide Data":
            self.disable_data()
            self.data_enabled = False
            self.hide_data.text = "Show Data"
        elif self.hide_data.text == "Show Data":    
            self.enable_data()
            self.data_enabled = True
            self.hide_data.text = "Hide Data"
    def enable_buttons(self):
        self.exit_button.enabled = True   
        self.hide_data.enabled = True
        self.start_stop_button.enabled = True
        self.grid.enabled = True
        self.repeat_button.enabled = True
        self.units_menu.enabled = True
        self.start_stop_button.enabled = True
    def disable_buttons(self):    
        self.exit_button.enabled = False   
        self.hide_data.enabled = False
        self.start_stop_button.enabled = False
        self.grid.enabled = False
        self.repeat_button.enabled = False
        self.units_menu.enabled = False
        self.start_stop_button.enabled = False
    def disable_data(self):
        self.time_now.enabled = False
        self.time_end.enabled = False
        self.sun_rise_set.enabled = False
        self.moon_rise_set.enabled = False
        self.moon_new_full.enabled = False
        self.moon_brightness.enabled = False
        self.earth_moon.enabled = False
        self.mercury_earth.enabled = False
        self.venus_earth.enabled = False
        self.mars_earth.enabled = False
        self.jupiter_earth.enabled = False
        self.saturn_earth.enabled = False
        self.uranus_earth.enabled = False
        self.neptune_earth.enabled = False
        self.mercury_sun.enabled = False
        self.venus_sun.enabled = False
        self.earth_sun.enabled = False
        self.mars_sun.enabled = False
        self.jupiter_sun.enabled = False
        self.saturn_sun.enabled = False
        self.uranus_sun.enabled = False
        self.neptune_sun.enabled = False
        self.moon_orbits.enabled = False
        self.mercury_days.enabled = False
        self.venus_days.enabled = False
        self.earth_days.enabled = False
        self.mars_days.enabled = False
        self.jupiter_days.enabled = False
        self.saturn_days.enabled = False
        self.uranus_days.enabled = False
        self.sun_nearest.enabled = False
        self.moon_nearest.enabled = False
        self.mercury_nearest.enabled = False
        self.venus_nearest.enabled = False
        self.mars_nearest.enabled = False
        self.jupiter_nearest.enabled = False
        self.saturn_nearest.enabled = False
        self.uranus_nearest.enabled = False
    def enable_data(self):
        self.time_now.enabled = True
        self.time_end.enabled = True
        self.sun_rise_set.enabled = True
        self.moon_rise_set.enabled = True
        self.moon_new_full.enabled = True
        self.moon_brightness.enabled = True
        self.earth_moon.enabled = True
        self.mercury_earth.enabled = True
        self.venus_earth.enabled = True
        self.mars_earth.enabled = True
        self.jupiter_earth.enabled = True
        self.saturn_earth.enabled = True
        self.uranus_earth.enabled = True
        self.neptune_earth.enabled = True
        self.mercury_sun.enabled = True
        self.venus_sun.enabled = True
        self.earth_sun.enabled = True
        self.mars_sun.enabled = True
        self.jupiter_sun.enabled = True
        self.saturn_sun.enabled = True
        self.uranus_sun.enabled = True
        self.neptune_sun.enabled = True
        self.moon_orbits.enabled = True
        self.mercury_days.enabled = True
        self.venus_days.enabled = True
        self.earth_days.enabled = True
        self.mars_days.enabled = True
        self.jupiter_days.enabled = True
        self.saturn_days.enabled = True
        self.uranus_days.enabled = True
        self.sun_nearest.enabled = True
        self.moon_nearest.enabled = True
        self.mercury_nearest.enabled = True
        self.venus_nearest.enabled = True
        self.mars_nearest.enabled = True
        self.jupiter_nearest.enabled = True
        self.saturn_nearest.enabled = True
        self.uranus_nearest.enabled = True
    def toggle_repeat(self):
        if self.repeat:self.repeat = False
        else:self.repeat = True
        if self.repeat:self.repeat_button.text = 'Repeat is On'
        else:self.repeat_button.text = 'Repeat is Off'
    def toggle_run_pause(self, key, arg=None):
        if key == 'escape' or arg == "toggle":
            if (self.Old_Start_Time!=self.start_time.text or float(self.Old_Duration)!=float(self.duration.text) or float(self.Old_Increment)!=float(self.increment.text) or
                float(self.Old_Latitude)!=float(self.latitude.text) or float(self.Old_Longitude)!=float(self.longitude.text) or float(self.Old_Altitude)!=float(self.altitude.text)):
                self.Data_Ready=False
                self.Start_Time = Time(self.start_time.text)
                self.Increment_Days=float(self.increment.text) / 24# Days
                self.increment_days_lbl.text=(f'Days = {str(round(float(self.increment.text)/24,3))}')
                self.duration_days_lbl.text=(f'Days = {str(round(float(self.duration.text)*365.256,3))}')
                self.time_now.text=(f'Local Time Now: {self.start_time.text.replace('T','  Hrs: ')[:-4]}')
                self.Earth_Location=EarthLocation.from_geodetic(lon=float(self.longitude.text) * u.deg, lat=float(self.latitude.text) * u.deg, height=float(self.altitude.text) * u.m)
                self.sun.enabled=False
                self.disable_buttons()
                self.disable_data()
                self.disable_inputfields()   
            else:    
                application.paused = not application.paused
                self.planets["earth"].texture="earth_day"
                self.Data_Ready=True
                self.sun.enabled=True
                self.pause_menu.enabled = application.paused # Toggle visibility of the entire pause menu
            if application.paused:
                self.enable_buttons()
                if self.data_enabled:self.enable_data()
                self.enable_inputfields()   
                self.status.text="Paused For Modifications"
            else:
                if not self.data_enabled:self.disable_data()
                self.disable_inputfields()   
                self.planets["earth"].scale=0.5
                self.planets["earth"].rotation=(0,0,0)
                self.status.text=""
    def validate_float_realtime(self, input_field):
        if input_field.text:# Only try to convert if there is some text
            try:
                float(input_field.text)
                input_field.text_field.color = color.green # Valid
            except ValueError:
                input_field.text_field.color = color.red # Invalid
        else:
            input_field.text_field.color = color.white
        if input_field==self.increment:
            try:
                self.increment_days_lbl.text=(f'Days = {str(round(float(self.increment.text)/24,3))}')
            except:    
                self.increment_days_lbl.text=(f'Days = ')
        elif input_field==self.duration:         
            try:
                self.duration_days_lbl.text=(f'Days = {str(round(float(self.duration.text)*365.256,3))}')
            except:    
                self.increment_days_lbl.text=(f'Days = ')
    def show_message(self, title, msg):
        wp = WindowPanel(
            title=title,
            content=(Text(msg), Button(text='Close', color=color.azure, on_click=lambda: destroy(wp))),)
    def get_moon_properties(self,utc_datetime):
        try:
            # Time analysis config (stepsize, duration, init time)
            init_time: Time = Time(utc_datetime, scale="utc")
            date_only = init_time.datetime.date()
            dt = TimeDelta(self.Increment_Days, format="jd")  # stepsize in days
            duration = TimeDelta(30.0, format="jd")  # duration
            # Generate observation time list
            dt_list = dt * np.arange(0, duration.jd / dt.jd, 1)
            obs_times: Time = init_time + dt_list
            # Generate Sun, Moon coordinates
            sun_vec_gcrs: SkyCoord = get_sun(obs_times).cartesian
            moon_vec_gcrs: SkyCoord = get_body(body="moon", time=obs_times, location=self.Earth_Location, 
                                               ephemeris=solar_system_ephemeris.get()).cartesian
            # Generate Earth location in GCRS 
            gnd_loc_gcrs = self.Earth_Location.get_gcrs(obs_times).cartesian.without_differentials()
            # Generate Sun, Moon to Local vectors
            sun_to_moon: CartesianRepresentation = sun_vec_gcrs - moon_vec_gcrs
            gnd_to_moon: CartesianRepresentation = gnd_loc_gcrs - moon_vec_gcrs
            # Compute angle between two vectors for each instant in time
            sun_to_moon_unit = sun_to_moon / sun_to_moon.norm()
            gnd_to_moon_unit = gnd_to_moon / gnd_to_moon.norm()
            phase_angle_moon = np.rad2deg(np.arccos(sun_to_moon_unit.dot(gnd_to_moon_unit)))
            brightness = (1 + np.cos(phase_angle_moon)) / 2 * 100
            percent_illumination = round(brightness,5)
            # Find New Moon And Full Moon
            full_moon_index_search, = np.where(phase_angle_moon == phase_angle_moon.min())
            new_moon_index_search, = np.where(phase_angle_moon == phase_angle_moon.max())
            full_moon_index = full_moon_index_search[0]  # numpy.where outputs a tuple, use first element
            new_moon_index = new_moon_index_search[0]  # numpy.where outputs a tuple, use first element
            full_moon_time = obs_times[full_moon_index]
            new_moon_time = obs_times[new_moon_index]
            full_moon_date=full_moon_time.to_datetime(timezone=self.Time_Zone).date()
            new_moon_date=new_moon_time.to_datetime(timezone=self.Time_Zone).date()
            moon_list=["Next New Moon / Full Moon:","Moon Illumination:","Moon Phase:","Waxing","Waning"]
            if date_only==self.Moon_Date:
                self.New_Full_Moons.append(self.New_Full_Moons[-1])
            else:
                self.New_Full_Moons.append(f"{moon_list[0]} {new_moon_date} / {full_moon_date}")
                self.Moon_Date=date_only
            self.Moon_Illuminations.append(f"{moon_list[1]} {percent_illumination[0]}%")
            phase=str(round(phase_angle_moon[0],12))
            phase=phase.replace(" deg", "°")
            if full_moon_time.to_datetime(timezone=self.Time_Zone) < new_moon_time.to_datetime(timezone=self.Time_Zone):
                self.Moon_Phases.append(f"{moon_list[2]} {phase}, {moon_list[3]}")
            else:self.Moon_Phases.append(f"{moon_list[2]} {phase}, {moon_list[4]}")
        except:
            pass
    def get_moonrise_moonset(self,utc_datetime):
        try:
            dt_obj = utc_datetime.to_datetime()
            date_only=dt_obj.date()
            if len(self.Moon_RiseSet)>0 and date_only==self.last_moonrise:
                self.Moon_RiseSet.append(self.Moon_RiseSet[-1])
            else:
                self.last_moonrise=date_only
                title="Local Moonrise / Moonset:"
                location = LocationInfo(name="Earth Location", region="Earth", timezone=self.Time_Zone, 
                                        latitude=float(self.latitude.text), longitude=float(self.longitude.text))
                try:
                    rise = moonrise(location.observer, date=date_only)
                    moonrise_utc=Time(rise.strftime('%Y-%m-%d %H:%M:%S'))
                    moonrise_local=moonrise_utc.to_datetime(timezone=self.Time_Zone)
                    moon_rise=f'{moonrise_local.strftime('%H:%M:%S')}'
                except:
                    moon_rise = "Never Rises"
                try:        
                    set = moonset(location.observer, date=date_only)
                    moonset_utc=Time(set.strftime('%Y-%m-%d %H:%M:%S'))
                    moonset_local=moonset_utc.to_datetime(timezone=self.Time_Zone)
                    moon_set=f'{moonset_local.strftime('%H:%M:%S')}'
                except:
                    moon_set = "Never Sets"
                self.Moon_RiseSet.append(f"{title} {moon_rise} / {moon_set}")
        except Exception as e:
            if len(self.Moon_RiseSet)>0 and date_only==self.last_moonrise:
                self.Moon_RiseSet.append(self.Moon_RiseSet[-1])
            else:self.Moon_RiseSet.append(f"{title} None")    
    def get_sunrise_sunset(self,utc_datetime):
        try:
            dt_obj = utc_datetime.to_datetime()
            date_only=dt_obj.date()
            if len(self.Sun_RiseSet)>0 and date_only==self.last_sunrise:
                self.Sun_RiseSet.append(self.Sun_RiseSet[-1])
            else:
                self.last_sunrise=date_only
                title="Local Sunrise / Sunset:"
                self.last_sunrise=date_only
                location = LocationInfo(name="Earth Location", region="Earth", timezone=self.Time_Zone, 
                                        latitude=float(self.latitude.text), longitude=float(self.longitude.text))
                s = sun(location.observer, date=dt_obj.date())
                try:
                    sunrise_utc=Time(s['sunrise'].strftime('%Y-%m-%d %H:%M:%S'))
                    sunrise_local=sunrise_utc.to_datetime(self.Time_Zone)
                    sun_rise=f'{sunrise_local.strftime('%H:%M:%S')}'
                except:
                    sun_rise = "Never Rises"
                try:        
                    sunset_utc=Time(s['sunset'].strftime('%Y-%m-%d %H:%M:%S'))
                    sunset_local=sunset_utc.to_datetime(self.Time_Zone)
                    sun_set=f'{sunset_local.strftime('%H:%M:%S')}'
                except:    
                    sun_set = "Never Sets"
                self.Sun_RiseSet.append(f"{title} {sun_rise} / {sun_set}")
        except Exception as e:
            if len(self.Sun_RiseSet)>0 and date_only==self.last_sunrise:
                self.Sun_RiseSet.append(self.Sun_RiseSet[-1])
            else:self.Sun_RiseSet.append(f"{title} None")    
    def smooth_moon_path(self, window_length, xdata, ydata, zdata):
        # Smooth Out Moon's Wobble Created By Exaggerated X,Y,Z
        # This Only Affects Displayed Moon And Not Moon Data.
        # length must be odd and <= len(data), poly_order must be < length
        try:
            poly_order = 3
            x_list = list(savgol_filter(xdata, window_length, poly_order))
            y_list = list(savgol_filter(ydata, window_length, poly_order))
            z_list = list(savgol_filter(zdata, window_length, poly_order))
            return x_list, y_list, z_list 
        except Exception as e:
            pass
    def finalize_data(self):# Exaggerate Moons Orbit To Accomidate Size Of Earth. Add My Location On Earth Object
        self.Real_Moon=self.Planets_Data[3].copy()# Save Real Moon Data For Calculations
        earth,moon,moon_exagerated,temp={},{},{},[]
        moon_x,moon_y,moon_z =[],[],[]
        for e in range(0, len(self.Local_Time)):
            try:
                temp=[]
                earth[e]=[element for element in self.Planets_Data[2][e]]
                moon[e]=[element * 80 for element in self.Planets_Data[3][e]]
                combined=zip(earth[e],moon[e]) # Earth + Moon
                temp=[x+y for (x,y) in combined]#  Animated Moon Data = Earth + Moon Combined
                moon_exagerated[e]=[element for element in temp]
                if len(self.Local_Time) <= 45:#poly_order (3) * window_length(15) <= 45
                    self.Planets_Data[3][e]=moon_exagerated[e]# Switch Moon Data With Exagerated Data For Displayed Animation
                    try:
                        self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                        self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                        self.planets["earth"].rotation_y = self.progress_bar.value * -4
                    except Exception as e:
                        if e > 0:self.Planets_Data[3][e]=self.Planets_Data[3][e-1]
                else:# Smooth Out Moon's Wobble Created By Exaggerated X,Y,Z poly_order (3) * window_length(15) > 45
                    moon_x.append(moon_exagerated[e][0])
                    moon_y.append(moon_exagerated[e][1])
                    moon_z.append(moon_exagerated[e][2])
            except Exception as e:
                pass
        if len(self.Local_Time) > 45:#poly_order (3) * window_length(15) > 45
            window_length = 15
            x_smooth, y_smooth, z_smooth = self.smooth_moon_path(window_length, moon_x, moon_y, moon_z)
            for e in range(0, len(self.Local_Time)):
                try:
                    self.Planets_Data[3][e] = x_smooth[e], y_smooth[e], z_smooth[e]
                    self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                    self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                    self.planets["earth"].rotation_y = self.progress_bar.value * -4
                except Exception as e:
                    if e > 0:self.Planets_Data[3][e]=self.Planets_Data[3][e-1]
                    pass    
        for e in range(0, len(self.Local_Time)):
            self.get_sunrise_sunset(self.UTC_Time[e])
            self.get_moonrise_moonset(self.UTC_Time[e])
            self.get_moon_properties(self.UTC_Time[e])
            try:
                self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                self.planets["earth"].rotation_y = self.progress_bar.value * -4
            except:pass
        earth,moon,moon_exagerated,temp={},{},{},[]
        moon_x,moon_y,moon_z =[],[],[]
    def astropy_bodies(self):
        if self.start_time.text=='':return
        if float(self.duration.text)<=0 or self.duration.text=="" : return
        if self.Increment_Days<=0:return
        if float(self.increment.text)<=0 or self.increment.text=="" :return
        self.bar_thread_running=True
        self.reset_solar_system()
        self.disable_buttons()
        self.disable_data()
        self.disable_inputfields()
        self.progress_bar.enabled=True
        self.progress_bar.value=0
        self.start_stop_button.enabled=False
        self.Increment_days=float(self.increment.text) / 24
        span=(float(self.duration.text) * 365.256) / self.Increment_Days
        time_format = ("%Y-%m-%dT%H:%M:%S.%f")
        self.Local_Time=Time(self.start_time.text, location=self.Earth_Location) + np.arange(span) * u.hour * float(self.increment.text)
        self.progress_bar.text_entity.color = color.yellow
        self.status.text=f"Please Wait! Preparing JPL DE442.bsp Planetary Data. This May Take A while!"
        for e in range(0, len(self.Local_Time)):# Create UTC Time Object From Local Time Object
            time.sleep(0.01)    
            try:
                local_time_str = str(self.Local_Time[e])
                naive_local_dt = datetime.strptime(local_time_str, time_format)
                aware_local_dt = self.Time_Zone.localize(naive_local_dt)
                utc_dt = aware_local_dt.astimezone(pytz.utc)
                utc_time_str = utc_dt.strftime(time_format)
                self.UTC_Time.append(Time(utc_time_str))
            except:
                if e > 0:self.UTC_Time.append(self.UTC_Time[e-1])
                pass
            try:
                earth_rotation, angle_hours = self.get_earth_angle(self.Local_Time[e])# Degrees/hr.
                self.Earth_Rotation.append(earth_rotation)
            except:
                if e > 0:self.Earth_Rotation.append(self.Earth_Rotation[e-1])
                pass    
            try:
                self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                self.planets["earth"].rotation_y = self.progress_bar.value * -4
            except:pass
        name=[]
        sun={}
        self.Earth_Location=EarthLocation.from_geodetic(lon=float(self.longitude.text) * u.deg, lat=float(self.latitude.text) * u.deg, height=float(self.altitude.text) * u.m)
        solar_system_ephemeris.set(self.ephemeris_path)
        for e in range(0,len(self.UTC_Time)):# Sun
            try:
                sun_icrs = get_body_barycentric(body='sun', time=self.UTC_Time[e], ephemeris=solar_system_ephemeris.get())
                sun[e]=[np.double(sun_icrs.x/self.de442_divisor), np.double(sun_icrs.z/self.de442_divisor), 
                        np.double(sun_icrs.y/self.de442_divisor)]
            except:
                if e > 0:sun[e]=sun[e-1]
                pass    
            try:
                self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                self.planets["earth"].rotation_y = self.progress_bar.value * -5
            except:pass    
        for name, entity in self.planets.items():
            data={}
            for e in range(0,len(self.UTC_Time)):# de442s file is ~31 MB, and covers years 1950-2050
                if name=="moon":
                    try:       
                        moon_icrs=get_body(body="moon",time=self.UTC_Time[e], ephemeris=solar_system_ephemeris.get())
                        data[e]=[np.double(moon_icrs.cartesian.x/self.de442_divisor), np.double(moon_icrs.cartesian.z/self.de442_divisor), 
                                np.double(moon_icrs.cartesian.y/self.de442_divisor)]
                    except:
                        if e > 0:data[e]=data[e-1]
                        pass
                else:
                    try:
                        planet_icrs=get_body_barycentric(body=name, time=self.UTC_Time[e], ephemeris=solar_system_ephemeris.get())# ICRS = ICRF axes with the origin at the solar-system barycenter
                        data[e]=[np.double(planet_icrs.x/self.de442_divisor), np.double(planet_icrs.z/self.de442_divisor), 
                                np.double(planet_icrs.y/self.de442_divisor)]
                    except:
                        if e > 0:data[e]=data[e-1]
                        pass
                    data[e] = [x-y for x,y in zip(sun[e], data[e])]
                try:
                    if self.progress_bar.value>=50:
                        self.progress_bar.text_entity.color = color.black
                    self.Bar_value += float(100 / (13 * len(self.Local_Time)))
                    self.progress_bar.value = float(f"{self.Bar_value:.2f}")
                    self.planets["earth"].rotation_y = self.progress_bar.value * -4
                except:pass    
            self.Planets_Data.append(data)
        response = self.finalize_data()# Finalize Moon And My Location On Earth Data (observe_loc)
        self.progress_bar.value = 100
        time.sleep(1)
        self.progress_bar.value=0
        self.Bar_value=0
        self.progress_bar.enabled=False
        self.Data_Ready=True
        self.Old_Start_Time=self.start_time.text
        self.Old_Duration=self.duration.text
        self.Old_Increment=self.increment.text
        self.Old_Latitude=self.latitude.text
        self.Old_Longitude=self.longitude.text
        self.Old_Altitude=self.altitude.text
        self.bar_stop_event.set()
        self.bar_thread_running=False
        self.enable_inputfields()
        self.enable_buttons()
        if self.data_enabled:self.enable_data()
        self.status.text="All Planetary Data Is Now Ready! Select Start To Continue."
        self.time_end.text=(f'Local Time End: {str(self.Local_Time[-1]).replace('T','  Hrs: ')[:-4]}')
    def get_earth_angle(self, dt):    
        local_era = dt.earth_rotation_angle(longitude=float(self.longitude.text ) * u.deg)
        earth_angle_hours = Angle(local_era, unit = u.hourangle)
        earth_angle = local_era.to(u.degree)
        return earth_angle.value, earth_angle_hours.value
    def set_timezone(self):
        try:
            # Find timezone using latitude and longitude
            tf = TimezoneFinder()
            timeZone_str = tf.timezone_at(lng=float(self.longitude.text), lat=float(self.latitude.text))
            if timeZone_str=="America/New_York":# Washington DC 38.9072° N, -77.0369° W    
                zone="U.S./Eastern Time Zone"
            elif timeZone_str=="America/Chicago":# Huntsville Al. 34.729847° N, -86.5859011° W
                zone="U.S./Central Time Zone"
            elif timeZone_str=="America/Denver":# Denver Co. 39.7392° N, -104.9903° W    
                zone="U.S./Mountain Time Zone"    
            elif timeZone_str=="America/Phoenix":# Phoenix Az. 33.4482° N, -112.0777° W     
                zone="U.S./Mountain Std Time Zone"    
            elif timeZone_str=="America/Los_Angeles":# Los Angeles Ca. 34.0549° N, -118.2426° W
                zone="U.S./Pacific Time Zone"
            elif timeZone_str=="America/Anchorage":# Anchorage Ak. 61.2176° N, -149.8997° W
                zone="U.S./Alaska Time Zone" 
            elif timeZone_str=="Pacific/Honolulu":# Honolulu Ha. 21.3099° N, -157.8581° W
                zone="U.S./Hawaii-Aleutian Time Zone"
            else:zone=timeZone_str               
            self.Time_Zone=pytz.timezone(timeZone_str)
            self.time_zone_lbl.text=zone
            self.Earth_Location = EarthLocation.from_geodetic(lon=float(self.longitude.text) * u.deg, lat=float(self.latitude.text) * u.deg, height=float(self.altitude.text) * u.m)
        except:
            self.Earth_Location = EarthLocation.from_geodetic(lon=-86.5859011 * u.deg, lat=34.729847 * u.deg, height=214.884 * u.m)
            self.Time_Zone=pytz.timezone("U.S./Central Time Zone")
    def enable_inputfields(self):
        self.start_stop_button.text = "Start"
        self.increment_lbl.enabled=True
        self.increment_days_lbl.enabled=True
        self.increment.enabled=True
        self.duration_lbl.enabled=True
        self.duration.enabled=True
        self.duration_days_lbl.enabled=True
        self.start_time_lbl.enabled=True
        self.start_time.enabled=True
        self.zone_lbl.enabled = True
        self.time_zone_lbl.enabled = True
        self.latitude_lbl.enabled=True
        self.latitude.enabled=True
        self.longitude_lbl.enabled=True
        self.longitude.enabled=True
        self.altitude_lbl.enabled=True
        self.altitude.enabled=True
        self.inputfields_enabled=True
        self.delay_lbl.enabled=True
        self.delay.enabled=True
    def disable_inputfields(self):
        self.start_stop_button.text = "Pause"
        self.increment_lbl.enabled=False
        self.increment_days_lbl.enabled=False
        self.increment.enabled=False
        self.duration_lbl.enabled=False
        self.duration.enabled=False
        self.duration_days_lbl.enabled=False
        self.start_time_lbl.enabled=False
        self.start_time.enabled=False
        self.zone_lbl.enabled = False
        self.time_zone_lbl.enabled = False
        self.latitude_lbl.enabled=False
        self.latitude.enabled=False
        self.longitude_lbl.enabled=False
        self.longitude.enabled=False
        self.altitude_lbl.enabled=False
        self.altitude.enabled=False
        self.inputfields_enabled=False
        self.delay_lbl.enabled=False
        self.delay.enabled=False
    def update(self):
        if not application.paused and self.Data_Ready:
            if self.delay_executed:
                if float(self.delay.text)>=0.001:# No delay if < 1 msec.
                    self.timer=0
                    self.delay_executed=False
                self.time_now.text=(f'Local Time Now: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-4]}')
                pos_info = f'View:  X = {round(camera.world_position.xyz[0],10)},   Y = {round(camera.world_position.xyz[2],10)},  Z = {round(camera.world_position.xyz[1],10)}'
                self.pos_display.text = pos_info
                p=0
                for name, entity in self.planets.items():
                    xyz=self.Planets_Data[p][self.dt]
                    x,y,z=np.double(xyz[0]), np.double(xyz[1]),np.double(xyz[2]) 
                    entity.x = x * self.Scale_Factor
                    entity.y = y * self.Scale_Factor
                    entity.z = z * self.Scale_Factor
                    if name == "jupiter" or name == "venus":entity.rotation_y += float(self.increment.text) * self.sidereal_rotation[p] # Jupiter and Venus has reversed rotation
                    elif name == "earth":entity.rotation_y = self.Earth_Rotation[self.dt] * -1 # Astropy Rotation Data
                    else: entity.rotation_y -= float(self.increment.text) * self.sidereal_rotation[p]
                    p+=1
                    if p >= len(self.planets):p=0
                self.sun.rotation_y -= float(self.increment.text) * 0.6122449# Degrees/hr.
                if self.time_now.enabled:# If Data Enabled
                    # ***************Sun And Moon Properties***************
                    self.sun_rise_set.text=self.Sun_RiseSet[self.dt]
                    self.moon_rise_set.text=self.Moon_RiseSet[self.dt]
                    self.moon_new_full.text=f"{self.New_Full_Moons[self.dt]}" 
                    self.moon_brightness.text=self.Moon_Illuminations[self.dt]
                    # ***************Planets Distance To Earth***************
                    ear=self.Planets_Data[2][self.dt]#Earth Coordinates
                    earth_moon=np.sqrt((self.Real_Moon[self.dt][0])**2 + (self.Real_Moon[self.dt][1])**2 + (self.Real_Moon[self.dt][2])**2) * self.factor
                    self.earth_moon.text=(f'Moon Distance To Earth: {round(earth_moon, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[0][self.dt]#Mercury
                    mercury_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.mercury_earth.text=(f'Mercury Distance To Earth: {round(mercury_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[1][self.dt]#Venus
                    venus_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.venus_earth.text=(f'Venus Distance To Earth: {round(venus_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[8][self.dt]#Mars
                    mars_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.mars_earth.text=(f'Mars Distance To Earth: {round(mars_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[5][self.dt]#Jupiter
                    jupiter_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.jupiter_earth.text=(f'Jupiter Distance To Earth: {round(jupiter_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[6][self.dt]#Saturn
                    saturn_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.saturn_earth.text=(f'Saturn Distance To Earth: {round(saturn_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[7][self.dt]#Uranus
                    uranus_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.uranus_earth.text=(f'Uranus Distance To Earth: {round(uranus_earth, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[8][self.dt]#Neptune
                    neptune_earth=np.sqrt((np.double(xyz[0]) - np.double(ear[0]))**2 + (np.double(xyz[1]) - 
                                                np.double(ear[1]))**2 + (np.double(xyz[2]) - np.double(ear[2]))**2) * self.factor
                    self.neptune_earth.text=(f'Neptune Distance To Earth: {round(neptune_earth, 8)} {self.measurement_units}')
                    # **************Planets Distance To Sun***************
                    xyz=self.Planets_Data[0][self.dt]#Mercury
                    mercury_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.mercury_sun.text=(f'Mercury Distance To Sun: {round(mercury_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[1][self.dt]#Venus
                    venus_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.venus_sun.text=(f'Venus Distance To Sun: {round(venus_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[2][self.dt]#Earth
                    earth_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.earth_sun.text=(f'Earth Distance To Sun: {round(earth_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[8][self.dt]#Mars
                    mars_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.mars_sun.text=(f'Mars Distance To Sun: {round(mars_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[5][self.dt]#Jupiter
                    jupiter_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.jupiter_sun.text=(f'Jupiter Distance To Sun: {round(jupiter_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[6][self.dt]#Saturn
                    saturn_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.saturn_sun.text=(f'Saturn Distance To Sun: {round(saturn_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[7][self.dt]#Uranus
                    uranus_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.uranus_sun.text=(f'Uranus Distance To Sun: {round(uranus_sun, 8)} {self.measurement_units}')
                    xyz=self.Planets_Data[8][self.dt]#Neptune
                    neptune_sun=np.sqrt(np.double(xyz[0])**2 + np.double(xyz[1])**2 + np.double(xyz[2])**2) * self.factor
                    self.neptune_sun.text=(f'Neptune Distance To Sun: {round(neptune_sun, 8)} {self.measurement_units}')
                    # ***************Planets Rotations And Orbits ***************
                    self.earth_rotations = float(self.Increment_Days * (self.dt))
                    self.moon_orbits.text=(f'Moon Orbits Sun / Orbits Earth: {str(round(1 / 365.256 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / 27.3217,8))}')
                    self.mercury_days.text=(f'Mercury Rotations / Orbits: {str(round(23.9345 / 1407.6 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / 87.969, 8))}')
                    self.venus_days.text=(f'Venus Rotations / Orbits: {str(round(23.9345 / 5832.5 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / 224.701, 8))}')
                    self.earth_days.text=f"Earth Rotations / Orbits: {round(self.earth_rotations, 5)} / {round((self.earth_rotations / 365.256),5)}"
                    self.mars_days.text=(f'Mars Rotations / Orbits: {str(round(23.9345 / 24.6229 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / 686.980, 8))}')
                    self.jupiter_days.text=(f'Jupiter Rotations / Orbits: {str(round(23.9345 / 9.3333 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / float(sqrt(5.20**3) * 365.256), 8))}')
                    self.saturn_days.text=(f'Saturn Rotations / Orbits: {str(round(23.9345 / 10.56056 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / float(sqrt(9.54**3) *365.256), 8))}')
                    self.uranus_days.text=(f'Uranus Rotations / Orbits: {str(round(23.9345 / 17.23333 * (self.Increment_Days * self.dt),6))} / {str(round((self.Increment_Days * self.dt) / float(sqrt(19.2**3) *365.256), 8))}')
                    # ***************Planets Nearest Distance To Earth ***************
                    if earth_sun<=self.Sun_Near:
                        self.sun_nearest.text=f"Sun Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(earth_sun,8)} {self.measurement_units}"
                        self.Sun_Near=earth_sun
                    if earth_moon<=self.Moon_Near:
                        self.moon_nearest.text=f"Moon Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(earth_moon,8)} {self.measurement_units}"
                        self.Moon_Near=earth_moon
                    if mercury_earth<=self.Mercury_Near:
                        self.mercury_nearest.text=f"Mercury Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} /{round(mercury_earth,8)} {self.measurement_units}"
                        self.Mercury_Near=mercury_earth
                    if venus_earth<=self.Venus_Near:
                        self.venus_nearest.text=f"Venus Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(venus_earth,8)} {self.measurement_units}"
                        self.Venus_Near=venus_earth
                    if mars_earth<=self.Mars_Near:
                        self.mars_nearest.text=f"Mars Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(mars_earth,8)} {self.measurement_units}"
                        self.Mars_Near=mars_earth
                    if jupiter_earth<=self.Jupiter_Near:
                        self.jupiter_nearest.text=f"Jupiter Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(jupiter_earth,8)} {self.measurement_units}"
                        self.Jupiter_Near=jupiter_earth
                    if saturn_earth<=self.Saturn_Near:
                        self.saturn_nearest.text=f"Saturn Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(saturn_earth,8)} {self.measurement_units}"
                        self.Saturn_Near=saturn_earth
                    if uranus_earth<=self.Uranus_Near:
                        self.uranus_nearest.text=f"Uranus Nearest To Earth: {str(self.Local_Time[self.dt]).replace('T','  Hrs: ')[:-7]} / {round(uranus_earth,8)} {self.measurement_units}"
                        self.Uranus_Near=uranus_earth
                self.dt+=1
                if self.dt >= len(self.Local_Time):
                    self.dt=0
                    self.angle_dt=0
                    self.Sun_Near=10e15
                    self.Sun_Near=10e15
                    self.Moon_Near=10e15
                    self.Mercury_Near=10e15
                    self.Venus_Near=10e15
                    self.Mars_Near=10e15
                    self.Jupiter_Near=10e15
                    self.Saturn_Near=10e15
                    self.Uranus_Near=10e15
                    self.earth_angle_now=0
                    self.earth_total_rotation=0
                    if not self.repeat:self.toggle_run_pause("key", 'toggle')
            else:
                self.timer += time.dt #sec.
                if self.timer >= float(self.delay.text):self.delay_executed = True
        else:
            if not self.Data_Ready and not self.bar_thread_running:
                self.bar_thread = threading.Thread(target=self.astropy_bodies)
                self.bar_thread.start()
if __name__ == '__main__':
    scale_factor = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
    mon_width = ctypes.windll.user32.GetSystemMetrics(0) * scale_factor
    mon_height = ctypes.windll.user32.GetSystemMetrics(1) * scale_factor
    # Ursina Only Likes @1.778 Display Aspect Ratio
    # Convert All Resolutions To 1.778 (16:9)Aspect Ratio
    # Using Monitor Width As Baseline.
    window_size = (int(mon_width), int(mon_width / (16 / 9)))
    app=Ursina(size = window_size, fullscreen=False, borderless = True, vsync = False, development_mode=False, icon='earth.ico')
    window.position = (0.0, 0.0)
    window.always_on_top = True
    window.exit_button.enabled = False 
    window.color = color.black
    action = Our_Solar_System()
    app.run()

