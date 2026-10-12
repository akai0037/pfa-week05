# Ember Ruins: build the TD_Arena level (geometry, characters, pickups, lights, camera).
import math
ROOT = "/Game/TopDown"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = ues.get_editor_world()
assert world.get_path_name().endswith("TD_Arena"), world.get_path_name()

# clear anything from a previous build of this level
for a in actors.get_all_level_actors():
    if a.get_folder_path() and str(a.get_folder_path()).startswith("TD"):
        actors.destroy_actor(a)

MESH = {k: unreal.load_asset("/Engine/BasicShapes/%s.%s" % (k, k)) for k in ("Cube", "Sphere", "Cylinder", "Cone", "Plane")}
MAT = {}
def mat(n):
    if n not in MAT:
        MAT[n] = unreal.load_asset(ROOT + "/Materials/MI_TD_" + n)
    return MAT[n]

STATIC = unreal.ComponentMobility.STATIC
MOVABLE = unreal.ComponentMobility.MOVABLE
KW = unreal.AttachmentRule.KEEP_WORLD
count = [0]

def V(x, y, z): return unreal.Vector(float(x), float(y), float(z))
def R(roll=0, pitch=0, yaw=0): return unreal.Rotator(roll=float(roll), pitch=float(pitch), yaw=float(yaw))

def mk(mesh, loc, scale=(1, 1, 1), m=None, label=None, folder="TD", tags=(), movable=False,
       collide=False, rot=(0, 0, 0), parent=None, shadow=True):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, V(*loc), R(*rot))
    c = a.static_mesh_component
    c.set_mobility(MOVABLE if movable else STATIC)
    if mesh:
        c.set_static_mesh(MESH[mesh])
    if m:
        c.set_material(0, mat(m))
    a.set_actor_scale3d(V(*scale))
    if not collide:
        c.set_collision_profile_name("NoCollision")
    c.set_editor_property("cast_shadow", bool(shadow and mesh))
    if label:
        a.set_actor_label(label)
    a.set_folder_path(folder)
    a.tags = [unreal.Name(t) for t in tags]
    if parent is not None:
        a.attach_to_actor(parent, "", KW, KW, KW, False)
    count[0] += 1
    return a

def pivot(loc, label, folder, tags):
    """Empty movable root (scale 1) that visual parts attach to."""
    return mk(None, loc, label=label, folder=folder, tags=("TD",) + tuple(tags), movable=True)

def part(p, mesh, rel, scale, m, tags=(), rot=(0, 0, 0), shadow=True):
    base = p.get_actor_location()
    return mk(mesh, (base.x + rel[0], base.y + rel[1], base.z + rel[2]), scale, m,
              label=p.get_actor_label() + "_" + (tags[0].split(":")[-1] if tags else mesh),
              folder=p.get_folder_path(), tags=("TD_Part",) + tuple(tags), movable=True, rot=rot,
              parent=p, shadow=shadow)

def light(loc, color, intensity, radius, label, folder, parent=None, tags=()):
    L = actors.spawn_actor_from_class(unreal.PointLight, V(*loc), R())
    lc = L.point_light_component
    lc.set_mobility(MOVABLE)
    lc.set_intensity(float(intensity))
    lc.set_light_color(unreal.LinearColor(*color, 1.0))
    lc.set_attenuation_radius(float(radius))
    lc.set_cast_shadows(False)
    L.set_actor_label(label)
    L.set_folder_path(folder)
    L.tags = [unreal.Name(t) for t in tags]
    if parent is not None:
        L.attach_to_actor(parent, "", KW, KW, KW, False)
    count[0] += 1
    return L

# ---------------- arena: x -2000..2800, y -2000..2000, floor top at z=4
X0, X1, Y0, Y1 = -2000, 2800, -2000, 2000
mk("Cube", ((X0 + X1) / 2, 0, -50), ((X1 - X0 + 400) / 100, (Y1 - Y0 + 400) / 100, 1.0), "grout",
   "Floor_Base", "TD/Floor", ("TD_Floor",), collide=True, shadow=False)
T = 400
for i in range(int((X1 - X0) / T)):
    for j in range(int((Y1 - Y0) / T)):
        cx, cy = X0 + T * (i + 0.5), Y0 + T * (j + 0.5)
        mk("Cube", (cx, cy, 0), (3.92, 3.92, 0.08), "floor_a" if (i + j) % 2 else "floor_b",
           "Tile_%02d_%02d" % (i, j), "TD/Floor", ("TD_Floor",), collide=True, shadow=False)

WH = 300
def wall(x0, y0, x1, y1, label, m="wall", h=WH):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w = mk("Cube", (cx, cy, h / 2), ((x1 - x0) / 100, (y1 - y0) / 100, h / 100), m, label, "TD/Walls",
           ("TD_Wall",), collide=True)
    # darker cap stone on top
    mk("Cube", (cx, cy, h + 10), ((x1 - x0 + 20) / 100, (y1 - y0 + 20) / 100, 0.2), "pillar",
       label + "_Cap", "TD/Walls", (), shadow=False)
    return w

wall(X0 - 100, Y0 - 100, X1 + 100, Y0, "Wall_South")
wall(X0 - 100, Y1, X1 + 100, Y1 + 100, "Wall_North")
wall(X0 - 100, Y0, X0, Y1, "Wall_West")
wall(X1, Y0, X1 + 100, Y1, "Wall_East")
# divider A (courtyard | hall) with two openings
wall(-650, Y0, -550, -1200, "WallA_1")
wall(-650, -400, -550, 400, "WallA_2")
wall(-650, 1200, -550, Y1, "WallA_3")
# divider B (hall | sanctum) with the gate in the middle
wall(1050, Y0, 1150, -250, "WallB_1")
wall(1050, 250, 1150, Y1, "WallB_2")

def pillar(x, y, label, size=160, h=360, brazier=True):
    mk("Cube", (x, y, h / 2), (size / 100, size / 100, h / 100), "pillar", label, "TD/Props", ("TD_Wall",), collide=True)
    if brazier:
        mk("Cylinder", (x, y, h + 12), (0.9, 0.9, 0.25), "bowl", label + "_Bowl", "TD/Props")
        mk("Sphere", (x, y, h + 30), (0.55, 0.55, 0.35), "ember", label + "_Ember", "TD/Props", ("TD_Ember",), movable=True, shadow=False)
        light((x, y, h + 90), (1.0, 0.45, 0.12), 40, 1100, label + "_Light", "TD/Lights")

def brazier(x, y, label):
    mk("Cylinder", (x, y, 60), (0.35, 0.35, 1.2), "iron", label, "TD/Props", ("TD_Wall",), collide=True)
    mk("Cylinder", (x, y, 125), (0.8, 0.8, 0.2), "bowl", label + "_Bowl", "TD/Props")
    mk("Sphere", (x, y, 140), (0.5, 0.5, 0.3), "ember", label + "_Ember", "TD/Props", ("TD_Ember",), movable=True, shadow=False)
    light((x, y, 200), (1.0, 0.45, 0.12), 30, 900, label + "_Light", "TD/Lights")

def crate(x, y, label, s=1.2, yaw=0):
    mk("Cube", (x, y, 4 + s * 50), (s, s, s), "crate", label, "TD/Props", ("TD_Wall",), collide=True, rot=(0, 0, yaw))

# hall pillars
for i, (x, y) in enumerate([(-150, -700), (-150, 700), (650, -700), (650, 700)]):
    pillar(x, y, "Pillar_Hall_%d" % i)
# sanctum pillars
for i, (x, y) in enumerate([(1650, -950), (1650, 950), (2450, -950), (2450, 950)]):
    pillar(x, y, "Pillar_Sanctum_%d" % i)
# gate braziers
brazier(940, -420, "Brazier_Gate_S")
brazier(940, 420, "Brazier_Gate_N")
brazier(-1850, -1850, "Brazier_Court_SW")
brazier(-800, -1850, "Brazier_Court_SE")
# crates: courtyard nook guarding key 1, plus cover in the hall
for i, (x, y) in enumerate([(-1450, 1450), (-1450, 1580), (-1580, 1350), (-1250, -900), (-1130, -960),
                            (250, -1450), (380, -1580), (250, 1450), (380, 1580), (-1700, 400)]):
    crate(x, y, "Crate_%02d" % i, 1.2, (i * 23) % 40)

# ---------------- gate with 3 key sockets
gate = mk("Cube", (1100, 0, 164), (1.3, 5.0, 3.2), "iron", "Gate", "TD/Gate", ("TD", "TD_Gate"), movable=True, collide=True)
for k, y in enumerate((-140, 0, 140)):
    mk("Sphere", (1030, y, 230), (0.28, 0.28, 0.28), "socket_off", "Gate_Socket_%d" % k, "TD/Gate",
       ("TD_Part", "TD_Socket", "idx:%d" % k), movable=True, parent=gate)
for k, y in enumerate((-200, -100, 0, 100, 200)):
    mk("Cube", (1030, y, 80), (0.08, 0.12, 1.2), "gold", "Gate_Bar_%d" % k, "TD/Gate", ("TD_Part",), movable=True, parent=gate)

# ---------------- portal (inactive until the Warden falls)
portal = pivot((2450, 0, 4), "Portal", "TD/Portal", ("TD_Portal",))
part(portal, "Cylinder", (0, 0, 4), (2.6, 2.6, 0.06), "portal_off", ("part:disc",), shadow=False)
part(portal, "Cylinder", (0, 0, 300), (1.4, 1.4, 6.0), "portal", ("part:beam",), shadow=False)
for k in range(8):
    a = k / 8 * math.tau
    part(portal, "Cube", (math.cos(a) * 170, math.sin(a) * 170, 50), (0.25, 0.25, 1.0), "pillar", ("part:stone%d" % k,), rot=(0, 0, math.degrees(a)))
light((2450, 0, 200), (0.3, 0.85, 1.0), 0, 1400, "Portal_Light", "TD/Portal", parent=portal, tags=("TD_PortalLight",))

# ---------------- hero
hero = pivot((-1700, -200, 4), "Hero", "TD/Hero", ("TD_Player",))
part(hero, "Cylinder", (0, 0, 55), (0.62, 0.62, 1.0), "player", ("part:body",))
part(hero, "Cylinder", (-8, 0, 70), (0.75, 0.75, 0.75), "player", ("part:cape",), shadow=True)
part(hero, "Sphere", (0, 0, 135), (0.55, 0.55, 0.55), "skin", ("part:head",))
part(hero, "Cylinder", (0, 0, 160), (0.6, 0.6, 0.2), "steel", ("part:helm",))
part(hero, "Cube", (25, 0, 140), (0.1, 0.38, 0.08), "visor", ("part:visor",), shadow=False)
part(hero, "Cube", (6, -40, 70), (0.45, 0.1, 0.6), "steel", ("part:shield",))
part(hero, "Cube", (30, 52, 75), (1.1, 0.1, 0.07), "steel", ("part:sword",))
part(hero, "Cube", (-20, 52, 75), (0.12, 0.3, 0.1), "gold", ("part:hilt",))

# ---------------- enemies
def hp_bar(p, z, w=0.8):
    part(p, "Cube", (0, 0, z), (w, 0.1, 0.05), "bar", ("part:bar",), shadow=False)

def slime(i, x, y):
    p = pivot((x, y, 4), "Slime_%02d" % i, "TD/Enemies", ("TD_Enemy", "TD_Slime"))
    part(p, "Sphere", (0, 0, 38), (1.0, 1.0, 0.75), "slime", ("part:body",))
    for s in (-1, 1):
        part(p, "Sphere", (36, s * 17, 52), (0.13, 0.13, 0.16), "eye_black", ("part:eye",), shadow=False)
    hp_bar(p, 105)

def brute(i, x, y):
    p = pivot((x, y, 4), "Brute_%02d" % i, "TD/Enemies", ("TD_Enemy", "TD_Brute"))
    part(p, "Cube", (0, 0, 72), (1.2, 1.05, 1.35), "brute", ("part:body",))
    for s in (-1, 1):
        part(p, "Cone", (5, s * 42, 160), (0.22, 0.22, 0.45), "steel", ("part:horn",))
        part(p, "Cube", (61, s * 24, 110), (0.06, 0.16, 0.07), "brute_eye", ("part:eye",), shadow=False)
        part(p, "Cube", (25, s * 72, 45), (0.38, 0.38, 0.38), "brute", ("part:fist",))
    hp_bar(p, 190, 1.0)

def spitter(i, x, y):
    p = pivot((x, y, 4), "Spitter_%02d" % i, "TD/Enemies", ("TD_Enemy", "TD_Spitter"))
    part(p, "Cylinder", (0, 0, 45), (0.65, 0.65, 0.9), "spitter", ("part:body",))
    part(p, "Sphere", (0, 0, 118), (0.72, 0.72, 0.72), "spitter", ("part:head",))
    part(p, "Sphere", (30, 0, 124), (0.28, 0.28, 0.28), "spit_eye", ("part:eye",), shadow=False)
    hp_bar(p, 175)

def warden(x, y):
    p = pivot((x, y, 4), "Warden", "TD/Enemies", ("TD_Enemy", "TD_Warden"))
    part(p, "Cube", (0, 0, 118), (1.9, 1.7, 2.3), "warden", ("part:body",))
    for s in (-1, 1):
        part(p, "Cube", (30, s * 120, 95), (0.6, 0.6, 1.5), "warden", ("part:arm",))
        part(p, "Cube", (96, s * 40, 175), (0.07, 0.28, 0.12), "windup", ("part:eye",), shadow=False)
    for k, yy in enumerate((-55, 0, 55)):
        part(p, "Cone", (0, yy, 262), (0.35, 0.35, 0.55 if k != 1 else 0.75), "gold", ("part:crown",))
    hp_bar(p, 320, 2.2)

slime(0, -1100, 650); slime(1, -950, -350); slime(2, -1350, 1150)
slime(3, 0, -250); slime(4, 250, 350); slime(5, -300, 1350); slime(6, 450, -1250)
brute(0, 750, -1350); brute(1, 750, 1350)
spitter(0, 450, 0); spitter(1, 300, 1650); spitter(2, -250, -1500)
spitter(3, 2650, -1550); spitter(4, 2650, 1550)
warden(2150, 0)

# ---------------- pickups
def key(i, x, y):
    p = pivot((x, y, 4), "EmberKey_%d" % i, "TD/Pickups", ("TD_Key",))
    part(p, "Cube", (0, 0, 85), (0.32, 0.32, 0.32), "gold", ("part:gem",), rot=(45, 35, 0), shadow=False)
    part(p, "Cylinder", (0, 0, 6), (0.9, 0.9, 0.03), "gold", ("part:ring",), shadow=False)
    light((x, y, 140), (1.0, 0.7, 0.2), 25, 600, "EmberKey_%d_Light" % i, "TD/Pickups", parent=p)

def heart(i, x, y, tags=("TD_Heart",), hidden=False):
    p = pivot((x, y, 4), ("Heart_%d" if not hidden else "DropHeart_%d") % i, "TD/Pickups", tags)
    for s in (-1, 1):
        part(p, "Sphere", (0, s * 13, 70), (0.3, 0.3, 0.3), "heart", ("part:lobe",), shadow=False)
    part(p, "Cone", (0, 0, 48), (0.42, 0.42, 0.35), "heart", ("part:tip",), rot=(180, 0, 0), shadow=False)
    if hidden:
        p.set_actor_location(V(x, y, -3000), False, False)

key(0, -1750, 1720); key(1, 850, -1720); key(2, 850, 1720)
heart(0, -1000, -1650); heart(1, 250, 0); heart(2, 1500, 1650); heart(3, 1500, -1650)
for i in range(4):
    heart(i, 0, 0, ("TD_DropHeart",), hidden=True)

# ---------------- pools: orbs + shockwave
for i in range(24):
    o = mk("Sphere", (0, 0, -3000), (0.34, 0.34, 0.34), "orb", "Orb_%02d" % i, "TD/Pool", ("TD", "TD_Orb"), movable=True, shadow=False)
shock = mk("Cylinder", (0, 0, -3000), (1, 1, 0.04), "shock", "Shockwave", "TD/Pool", ("TD", "TD_Shock"), movable=True, shadow=False)

# ---------------- camera + on-screen titles (TextRender attached to the camera)
cam = actors.spawn_actor_from_class(unreal.CameraActor, V(-2450, -200, 1300), R(0, -58, 0))
cam.set_actor_label("TD_Camera"); cam.set_folder_path("TD/Camera"); cam.tags = [unreal.Name("TD"), unreal.Name("TD_Camera")]
cc = cam.camera_component
cc.set_editor_property("field_of_view", 55.0)
try:
    cc.set_editor_property("constrain_aspect_ratio", False)
except Exception:
    pass
for name, rel_z, size, tag in (("Title", 22, 34, "TD_Title"), ("Subtitle", -14, 11, "TD_Subtitle")):
    t = actors.spawn_actor_from_class(unreal.TextRenderActor, V(0, 0, 0), R())
    t.set_actor_label("TD_" + name); t.set_folder_path("TD/Camera"); t.tags = [unreal.Name("TD"), unreal.Name(tag)]
    tr = t.text_render
    tr.set_text("")
    tr.set_editor_property("world_size", float(size))
    try:
        tr.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
        tr.set_editor_property("vertical_alignment", unreal.VerticalTextAligment.EVRTA_TEXT_CENTER)
    except Exception as e:
        print("align:", e)
    tr.set_mobility(MOVABLE)
    t.attach_to_actor(cam, "", KW, KW, KW, False)
    t.root_component.set_relative_location_and_rotation(V(300, 0, rel_z), R(0, 0, 180), False, False)

# ---------------- sky + lighting (all movable: no light build needed)
sun = actors.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 1500), R(0, -52, -35))
sun.set_actor_label("TD_Sun"); sun.set_folder_path("TD/Lights")
dl = sun.light_component
dl.set_mobility(MOVABLE)
dl.set_intensity(4.0)
dl.set_light_color(unreal.LinearColor(0.78, 0.74, 1.0, 1))
try:
    dl.set_editor_property("atmosphere_sun_light", True)
except Exception:
    pass
sky = actors.spawn_actor_from_class(unreal.SkyLight, V(0, 0, 1600), R())
sky.set_actor_label("TD_SkyLight"); sky.set_folder_path("TD/Lights")
sl = sky.light_component
sl.set_mobility(MOVABLE)
try:
    sl.set_editor_property("real_time_capture", True)
except Exception:
    pass
sl.set_intensity(1.2)
atm = actors.spawn_actor_from_class(unreal.SkyAtmosphere, V(0, 0, 0), R())
atm.set_actor_label("TD_SkyAtmosphere"); atm.set_folder_path("TD/Lights")
fog = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, V(0, 0, 0), R())
fog.set_actor_label("TD_Fog"); fog.set_folder_path("TD/Lights")
try:
    fc = fog.component
    fc.set_editor_property("fog_density", 0.015)
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.25, 0.12, 0.2, 1))
except Exception as e:
    print("fog:", e)
ppv = actors.spawn_actor_from_class(unreal.PostProcessVolume, V(0, 0, 0), R())
ppv.set_actor_label("TD_PostProcess"); ppv.set_folder_path("TD/Lights")
ppv.set_editor_property("unbound", True)
try:
    s = ppv.settings
    s.set_editor_property("override_auto_exposure_min_brightness", True)
    s.set_editor_property("auto_exposure_min_brightness", 0.6)
    s.set_editor_property("override_auto_exposure_max_brightness", True)
    s.set_editor_property("auto_exposure_max_brightness", 1.4)
    s.set_editor_property("override_bloom_intensity", True)
    s.set_editor_property("bloom_intensity", 1.2)
    s.set_editor_property("override_vignette_intensity", True)
    s.set_editor_property("vignette_intensity", 0.55)
    ppv.set_editor_property("settings", s)
except Exception as e:
    print("ppv:", e)

# ---------------- world settings: our game mode (no default pawn)
ws = world.get_world_settings()
ws.set_editor_property("default_game_mode", unreal.EditorAssetLibrary.load_blueprint_class(ROOT + "/Blueprints/BP_TD_GameMode"))
print("game mode:", ws.get_editor_property("default_game_mode"))
print("actors spawned:", count[0])

# frame the editor view on the start area
ues.set_level_viewport_camera_info(V(-2450, -200, 1300), R(0, -58, 0))
