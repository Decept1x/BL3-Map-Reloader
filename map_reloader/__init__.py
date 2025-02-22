from mods_base import build_mod #type: ignore
from ui_utils import show_hud_message #type: ignore
from typing import Any #type: ignore
import unrealsdk #type: ignore
from unrealsdk import make_struct, find_all, find_object, find_class, construct_object #type: ignore
from mods_base import get_pc, hook, keybind, build_mod, ENGINE, SliderOption, BoolOption #type: ignore
from unrealsdk.hooks import Type, add_hook, Block, remove_hook, inject_next_call, prevent_hooking_direct_calls #type: ignore
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct #type: ignore
import math

map_name: str = ""
station: str = ""
counter: int = 1
spawn_location = None
spawn_rotation = None
vault_station_fallback = ""
map_overrides = ["Raid_P", "GuardianTakedown_P"]

@hook("/Script/GbxCameraModes.CameraBehavior:Update", Type.PRE)
def reset_map_load(obj: UObject, args: WrappedStruct, _3: Any, func: BoundFunction) -> None:
    global spawn_location, spawn_rotation, station
    # teleport player to correct location after map load
    get_pc().Pawn.K2_TeleportTo(spawn_location, spawn_rotation)
    for item in find_all("TravelStationResurrectComponent", False):
        if item.Outer.Name == station:
            # makes sure you re-hit the travel station you were teleported to
            # really only needed for level transitions
            item.ActivateTravelStation(True)
    reset_map_load.disable()

@hook("/Script/OakGame.TravelStationObject:OnTravelStationActivated", Type.POST)
def hit_save_station(obj: UObject, args: WrappedStruct, _3: Any, func: BoundFunction) -> None:
    global vault_station_fallback
    print(vault_station_fallback, obj, args, sep="\n")
    if ("VaultArch" in str(obj)) or ("ResurrectTravel" in str(obj) and "Trial" in str(obj)):
        # stores the previous NON vault travel station object when entering or exiting a vault
        # OR stores the previous NON mid-run new-u station when doing proving grounds (map fast travel)
        if "VaultArch" in str(args.OtherStation) or ("ResurrectTravel" in str(args.OtherStation) and "Trial" in str(args.OtherStation)):
            return
        vault_station_fallback = args.OtherStation.OakTravelStationResurrectComponent

def start_sq(obj: UObject, args: WrappedStruct, _3: Any, func: BoundFunction) -> None:
    # makes sure the game saves before reloading the map as doing both a save and reload in the same function causes the save to not work
    get_location_and_save()

def reload_map():
    global map_name, map_overrides
    # reloads the map you are currently in
    find_class("GameplayStatics").ClassDefaultObject.OpenLevel(get_pc(), map_name, True, "")
    reset_map_load.enable()

def qtd_pressed(obj: UObject, args: WrappedStruct, _3: Any, func: BoundFunction) -> type[Block] | None:
    global map_name, map_overrides
    if args.ChoiceNameId == "GbxMenu_Secondary1": # quit to main menu button
        if map_name in map_overrides:
            return
        else:
            reload_map()
            return Block
    if args.ChoiceNameId == "QuitToDesktop": # quit to desktop button
        with prevent_hooking_direct_calls():
            # acts as if you pressed the save quit button instead, allows user to go to the main menu
            func(args.SourceDialog, "GbxMenu_Secondary1", make_struct("GbxMenuInputEvent"))
        return Block
    else: # does nothing if cancel button is pressed
        return

def get_location_and_save():
    global spawn_location, spawn_rotation, station, map_name, vault_station_fallback
    map_name = str(ENGINE.GameViewport.World.CurrentLevel.OwningWorld.Name)
    if "MenuMap_P" not in map_name: # makes sure to not work while in main menu (keybind only)
        for item in find_all("TravelStationResurrectComponent", False): # finds all new-us
            if item.StationIsActive is True:
                if ("VaultArch" in str(item)) or ("ResurrectTravel" in str(item) and "Trial" in str(item)):
                    item = vault_station_fallback
                item.Outer.OnTravelStationActivated(None) # saves game
                station = str(item.Outer.Name)
                station_location = item.AttachParent.RelativeLocation # location of the new-u mesh
                station_rotation = item.AttachParent.RelativeRotation # rotation of the new-u mesh
                spawn_location = item.Outer.TravelStationSpawnPoint1.RelativeLocation # location of solo spawn point
                spawn_rotation = item.Outer.TravelStationSpawnPoint1.RelativeRotation # rotation of solo spawn point
                # The spawn locations are stored relative to the skeletal mesh of the new-u station
                # So, we need to get the location of the spawn point relative to the world grid which requires a rotation matrix
                # We then add the location of the skeletal mesh (station_location) and the NEW location of the spawn point (rel_spawn_loc_x, rel_spawn_loc_y)
                # to get the players actual spawn location relative to the world grid
                rel_spawn_loc_x = spawn_location.X * math.cos(math.radians(station_rotation.Yaw)) - spawn_location.Y * math.sin(math.radians(station_rotation.Yaw))
                rel_spawn_loc_y = spawn_location.X * math.sin(math.radians(station_rotation.Yaw)) + spawn_location.Y * math.cos(math.radians(station_rotation.Yaw))
                spawn_location = make_struct(
                    "Vector",
                    X=station_location.X + rel_spawn_loc_x,
                    Y=station_location.Y + rel_spawn_loc_y,
                    Z=station_location.Z + spawn_location.Z,
                )
                spawn_rotation = make_struct(
                    "Rotator",
                    Pitch=0,
                    Yaw=station_rotation.Yaw + spawn_rotation.Yaw,
                    Roll=0,
                )

def button_override(setting, new_value):
    if new_value is True:
        add_hook("/Script/OakGame.GFxPauseMenu:OnQuitClicked", Type.PRE, "start_sq", start_sq)
        add_hook("/Script/OakGame.GFxPauseMenu:OnQuitChoiceMade", Type.PRE, "qtd_pressed", qtd_pressed)
    else:
        remove_hook("/Script/OakGame.GFxPauseMenu:OnQuitClicked", Type.PRE, "start_sq")
        remove_hook("/Script/OakGame.GFxPauseMenu:OnQuitChoiceMade", Type.PRE, "qtd_pressed")


@keybind("hidden", is_hidden=True, event_filter=1)
def save_quit_secret():
    global map_name
    save_quit_secret.key = None
    find_class("GameplayStatics").ClassDefaultObject.OpenLevel(get_pc(), map_name, True, "")
    reset_map_load.enable()
    return

@keybind("Reload Map", event_filter=0)
def save_quit():
    save_quit_secret.key = save_quit.key
    get_location_and_save()
    return

button_override_option = BoolOption(
    "Override Pause Menu Buttons",
    False,
    "Yes",
    "No",
    on_change=button_override,
    description="Changes the functionality of the buttons in the pause menu.\n\"Quit to Main Menu\" -> Reloads Map\n\"Quit to Desktop\" -> \"Quit to Main Menu\""
)


build_mod(options=[button_override_option], hooks=[hit_save_station])

