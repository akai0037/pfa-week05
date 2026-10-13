# bridge: no-transaction
# Ember Ruins setup 1: master material, material instances, game mode, new level.
MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
ROOT = "/Game/TopDown"

def ensure_dir(p):
    if not EAL.does_directory_exist(p):
        EAL.make_directory(p)
for d in ("Materials", "Blueprints", "Maps"):
    ensure_dir(ROOT + "/" + d)

# --- master material: Color -> BaseColor, Color*Glow -> Emissive
mpath = ROOT + "/Materials/M_TD_Base"
if EAL.does_asset_exist(mpath):
    master = unreal.load_asset(mpath)
else:
    master = tools.create_asset("M_TD_Base", ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    col = MEL.create_material_expression(master, unreal.MaterialExpressionVectorParameter, -600, 0)
    col.set_editor_property("parameter_name", "Color")
    col.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1))
    glow = MEL.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -600, 250)
    glow.set_editor_property("parameter_name", "Glow")
    glow.set_editor_property("default_value", 0.0)
    rough = MEL.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -600, 400)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.6)
    mul = MEL.create_material_expression(master, unreal.MaterialExpressionMultiply, -300, 200)
    MEL.connect_material_expressions(col, "", mul, "A")
    MEL.connect_material_expressions(glow, "", mul, "B")
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.recompile_material(master)
print("master:", master.get_path_name())

PALETTE = {
    "floor_a": ((0.050, 0.048, 0.058), 0, 0.85), "floor_b": ((0.072, 0.066, 0.072), 0, 0.85),
    "grout": ((0.015, 0.014, 0.018), 0, 0.9), "wall": ((0.20, 0.155, 0.13), 0, 0.8),
    "pillar": ((0.27, 0.22, 0.18), 0, 0.75), "crate": ((0.33, 0.20, 0.09), 0, 0.7),
    "iron": ((0.07, 0.07, 0.085), 0, 0.4), "bowl": ((0.04, 0.04, 0.045), 0, 0.5),
    "ember": ((1.0, 0.33, 0.05), 14, 0.5),
    "player": ((0.07, 0.28, 0.85), 0, 0.45), "skin": ((0.85, 0.64, 0.5), 0, 0.6),
    "steel": ((0.72, 0.74, 0.8), 0, 0.25), "visor": ((0.2, 0.9, 1.0), 8, 0.3),
    "sword_glow": ((0.45, 0.95, 1.0), 14, 0.2),
    "slime": ((0.14, 0.72, 0.2), 0.35, 0.3), "brute": ((0.58, 0.08, 0.06), 0, 0.6),
    "brute_eye": ((1.0, 0.85, 0.2), 10, 0.5), "spitter": ((0.38, 0.1, 0.68), 0, 0.5),
    "spit_eye": ((1.0, 0.2, 0.9), 12, 0.3), "orb": ((1.0, 0.25, 0.9), 18, 0.3),
    "warden": ((0.22, 0.03, 0.06), 0, 0.5), "gold": ((1.0, 0.68, 0.15), 7, 0.3),
    "eye_black": ((0.01, 0.01, 0.01), 0, 0.2),
    "heart": ((1.0, 0.1, 0.15), 7, 0.3), "bar": ((1.0, 0.18, 0.1), 5, 0.5),
    "flash": ((1.0, 1.0, 1.0), 4, 0.5), "hurt": ((1.0, 0.08, 0.08), 6, 0.5),
    "windup": ((1.0, 0.5, 0.05), 8, 0.5),
    "socket_off": ((0.06, 0.05, 0.05), 0, 0.6),
    "portal_off": ((0.09, 0.11, 0.14), 0, 0.5), "portal": ((0.2, 0.85, 1.0), 12, 0.3),
    "shock": ((1.0, 0.5, 0.1), 10, 0.5),
}
for name, (rgb, glow, rough) in PALETTE.items():
    path = ROOT + "/Materials/MI_TD_" + name
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = tools.create_asset("MI_TD_" + name, ROOT + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, master)
    MEL.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    MEL.set_material_instance_scalar_parameter_value(mi, "Glow", float(glow))
    MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", float(rough))
print("material instances:", len(PALETTE))

# --- game mode with no default pawn (Python drives the hero)
gpath = ROOT + "/Blueprints/BP_TD_GameMode"
if EAL.does_asset_exist(gpath):
    bp = unreal.load_asset(gpath)
else:
    f = unreal.BlueprintFactory()
    f.set_editor_property("parent_class", unreal.GameModeBase)
    bp = tools.create_asset("BP_TD_GameMode", ROOT + "/Blueprints", unreal.Blueprint, f)
gen = unreal.BlueprintEditorLibrary.generated_class(bp)
cdo = unreal.get_default_object(gen)
try:
    cdo.set_editor_property("default_pawn_class", None)
except Exception as e:
    print("default_pawn_class None failed:", e)
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
print("default pawn now:", cdo.get_editor_property("default_pawn_class"))

EAL.save_directory(ROOT, only_if_is_dirty=False, recursive=True)

# --- new empty level
ok = level.new_level(ROOT + "/Maps/TD_Arena")
print("new level:", ok, unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name())
