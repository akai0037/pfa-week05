"""EMBER RUINS - a small top-down action-adventure, driven by Python during Play In Editor.

Load the TD_Arena level and press Play. This module ticks with the editor; when it sees the
Play-In-Editor world containing the Ember Ruins actors (tagged "TD") it runs the game.

Controls: WASD / arrows move, mouse aims, Space or Left Click attack, Shift dash, R restart.
Install manually with:  import td_game; td_game.install()
"""
import math, random, builtins
import unreal

ROOT = "/Game/TopDown"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
GS = unreal.GameplayStatics
SL = unreal.SystemLibrary

# ------------------------------------------------------------------ tuning
P_SPEED = 620.0
P_RADIUS = 40.0
P_MAX_HP = 6
DASH_SPEED, DASH_TIME, DASH_CD = 1750.0, 0.16, 0.65
ATK_TIME, ATK_CD, ATK_REACH, ATK_ARC = 0.20, 0.30, 175.0, 80.0
INVULN = 1.2
START_GRACE = 2.5   # seconds before enemies can notice you
CAM_OFFSET = (-900.0, 0.0, 1450.0)
CAM_FOV = 62.0
CAM_PITCH = -58.0

KINDS = {
    #            hp  radius speed  aggro  touch
    "Slime":   (2,   45,    200,   650,   1),
    "Brute":   (5,   68,    170,   1000,  1),
    "Spitter": (3,   42,    210,   1050,  1),
    "Warden":  (16,  115,   150,   99999, 2),
}

def V(x, y, z):
    return unreal.Vector(float(x), float(y), float(z))

def R(yaw=0.0, pitch=0.0, roll=0.0):
    return unreal.Rotator(roll=float(roll), pitch=float(pitch), yaw=float(yaw))

def tagset(a):
    return set(str(t) for t in a.tags)

def mkkey(name):
    k = unreal.Key()
    k.import_text(name)
    return k

def ang_diff(a, b):
    d = (a - b + 180.0) % 360.0 - 180.0
    return abs(d)

def lerp(a, b, t):
    return a + (b - a) * t


class Part(object):
    """A visual piece attached to an entity pivot."""
    def __init__(self, actor):
        self.a = actor
        self.comp = actor.root_component
        # copy the structs: get_editor_property can hand back live views of the component
        l = self.comp.get_editor_property("relative_location")
        r = self.comp.get_editor_property("relative_rotation")
        s = self.comp.get_editor_property("relative_scale3d")
        self.loc0 = unreal.Vector(l.x, l.y, l.z)
        self.rot0 = unreal.Rotator(roll=r.roll, pitch=r.pitch, yaw=r.yaw)
        self.scl0 = unreal.Vector(s.x, s.y, s.z)
        smc = getattr(actor, "static_mesh_component", None)
        self.smc = smc
        self.mat0 = smc.get_material(0) if smc else None
        self.cur_mat = self.mat0

    def set_rel(self, loc=None, rot=None):
        self.comp.set_relative_location_and_rotation(loc or self.loc0, rot or self.rot0, False, False)

    def set_scale(self, sx, sy, sz):
        self.a.set_actor_relative_scale3d(V(sx, sy, sz))

    def set_mat(self, m):
        if self.smc and m is not self.cur_mat:
            self.smc.set_material(0, m)
            self.cur_mat = m

    def reset(self):
        self.set_rel()
        self.a.set_actor_relative_scale3d(self.scl0)
        self.set_mat(self.mat0)


class Ent(object):
    """Anything with a pivot actor + attached parts."""
    def __init__(self, actor, kind):
        self.a = actor
        self.kind = kind
        l = actor.get_actor_location()
        self.x0, self.y0, self.z0 = l.x, l.y, l.z
        self.yaw0 = actor.get_actor_rotation().yaw
        self.parts = {}
        self.lights = []
        for c in actor.get_attached_actors():
            if isinstance(c, unreal.PointLight):
                self.lights.append((c, c.point_light_component.intensity))
                continue
            role = "misc"
            for t in tagset(c):
                if t.startswith("part:"):
                    role = t[5:]
            self.parts.setdefault(role, []).append(Part(c))
        self.reset()

    def reset(self):
        self.x, self.y, self.z = self.x0, self.y0, self.z0
        self.yaw = self.yaw0
        self.vx = self.vy = 0.0
        self.kx = self.ky = 0.0
        self.t = random.random() * 10
        self.state = "idle"
        self.st = 0.0
        self.cd = 1.0 + random.random()
        self.flash = 0.0
        self.alive = True
        self.dying = 0.0
        self.awake = False
        self.strafe = random.choice((-1, 1))
        self.lock = (1.0, 0.0)
        self.touch_cd = 0.0
        if self.kind in KINDS:
            self.hp = KINDS[self.kind][0]
            self.r = KINDS[self.kind][1]
        for ps in self.parts.values():
            for p in ps:
                p.reset()
        self.set_hidden(False)
        self.sync()

    def set_hidden(self, h):
        self.a.set_actor_hidden_in_game(h)
        for ps in self.parts.values():
            for p in ps:
                p.a.set_actor_hidden_in_game(h)
        for L, inten in self.lights:
            L.point_light_component.set_intensity(0.0 if h else inten)
        self.hidden = h

    def sync(self):
        self.a.set_actor_location_and_rotation(V(self.x, self.y, self.z), R(self.yaw), False, False)

    def each(self, role):
        return self.parts.get(role, [])


class Game(object):
    def __init__(self, world):
        self.world = world
        self.pc = GS.get_player_controller(world, 0)
        self.mats = {}
        self.keys = {n: mkkey(n) for n in ("W", "A", "S", "D", "Up", "Down", "Left", "Right",
                                            "SpaceBar", "LeftMouseButton", "LeftShift", "RightShift", "R")}
        tagged = list(GS.get_all_actors_with_tag(world, "TD"))
        by = lambda t: [a for a in tagged if t in tagset(a)]
        self.cam = by("TD_Camera")[0]
        self.title = by("TD_Title")[0].text_render
        self.subtitle = by("TD_Subtitle")[0].text_render
        self.player = Ent(by("TD_Player")[0], "Player")
        self.enemies = []
        for a in by("TD_Enemy"):
            kind = [k for k in KINDS if ("TD_" + k) in tagset(a)][0]
            self.enemies.append(Ent(a, kind))
        self.warden = [e for e in self.enemies if e.kind == "Warden"][0]
        self.keys_ents = [Ent(a, "Key") for a in by("TD_Key")]
        self.hearts = [Ent(a, "Heart") for a in by("TD_Heart")]
        self.drop_hearts = [Ent(a, "Heart") for a in by("TD_DropHeart")]
        self.orbs = [{"a": a, "on": False} for a in by("TD_Orb")]
        self.shock = by("TD_Shock")[0]
        self.portal = Ent(by("TD_Portal")[0], "Portal")
        self.gate = by("TD_Gate")[0]
        gl = self.gate.get_actor_location()
        self.gate_z0 = gl.z
        self.sockets = []
        for c in self.gate.get_attached_actors():
            ts = tagset(c)
            if "TD_Socket" in ts:
                idx = int([t for t in ts if t.startswith("idx:")][0][4:])
                self.sockets.append((idx, Part(c)))
        self.sockets.sort(key=lambda s: s[0])
        o, ext = self.gate.get_actor_bounds(False)
        self.gate_rect = (o.x - ext.x, o.y - ext.y, o.x + ext.x, o.y + ext.y)
        self.walls = []
        for w in GS.get_all_actors_with_tag(world, "TD_Wall"):
            o, ext = w.get_actor_bounds(False)
            self.walls.append((o.x - ext.x, o.y - ext.y, o.x + ext.x, o.y + ext.y))
        self.embers = [(a, None) for a in GS.get_all_actors_with_tag(world, "TD_Ember")]
        self.last_mouse = None
        self.god = False   # debug: the hero takes no damage
        self.restart(first=True)

    # ---------------------------------------------------------------- helpers
    def mat(self, n):
        if n not in self.mats:
            self.mats[n] = unreal.load_asset(ROOT + "/Materials/MI_TD_" + n)
        return self.mats[n]

    def down(self, *names):
        return any(self.pc.is_input_key_down(self.keys[n]) for n in names)

    def pressed(self, *names):
        return any(self.pc.was_input_key_just_pressed(self.keys[n]) for n in names)

    def solids(self):
        return self.walls + ([self.gate_rect] if self.gate_solid else [])

    def collide(self, x, y, r):
        for (x0, y0, x1, y1) in self.solids():
            qx = min(max(x, x0), x1)
            qy = min(max(y, y0), y1)
            dx, dy = x - qx, y - qy
            d2 = dx * dx + dy * dy
            if d2 < r * r:
                if d2 > 1e-6:
                    d = math.sqrt(d2)
                    x += dx / d * (r - d)
                    y += dy / d * (r - d)
                else:  # centre inside the box: push out the short way
                    pens = ((x - x0 + r, -1, 0), (x1 - x + r, 1, 0), (y - y0 + r, 0, -1), (y1 - y + r, 0, 1))
                    p, sx, sy = min(pens)
                    x += sx * p
                    y += sy * p
        return x, y

    def blocked(self, x, y, pad=0.0):
        for (x0, y0, x1, y1) in self.solids():
            if x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad:
                return True
        return False

    def move(self, e, dx, dy):
        nx, ny = self.collide(e.x + dx, e.y + dy, e.r)
        hit = abs((nx - e.x) - dx) + abs((ny - e.y) - dy) > 1.0
        e.x, e.y = nx, ny
        return hit

    def say(self, title, sub="", t=2.5, color=(255, 210, 120)):
        self.title.set_text(title)
        self.subtitle.set_text(sub)
        self.title.set_text_render_color(unreal.Color(r=color[0], g=color[1], b=color[2], a=255))
        self.subtitle.set_text_render_color(unreal.Color(r=235, g=235, b=245, a=255))
        self.msg_t = t

    def hud(self, key, text, rgb, dur=0.25):
        SL.print_string(self.world, text, True, False, unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0), dur, key)

    def add_shake(self, amount):
        self.shake = max(self.shake, amount)

    # ---------------------------------------------------------------- lifecycle
    def restart(self, first=False):
        p = self.player
        p.reset()
        p.r = P_RADIUS
        p.hp = P_MAX_HP
        p.inv = 0.0
        p.dash_t = p.dash_cd = 0.0
        p.atk_t = p.atk_cd = 0.0
        p.swing_dir = 1
        p.aim_mouse = 0.0
        p.dash_dir = (1.0, 0.0)
        for e in self.enemies:
            e.reset()
            self.update_bar(e)
        for k in self.keys_ents + self.hearts:
            k.reset()
            k.taken = False
        for h in self.drop_hearts:
            h.reset()
            h.taken = True
            h.set_hidden(True)
            h.z = -3000
            h.sync()
        for o in self.orbs:
            self.kill_orb(o)
        self.shock.set_actor_location(V(0, 0, -3000), False, False)
        self.shock_t = -1.0
        self.keys_found = 0
        for idx, s in self.sockets:
            s.set_mat(self.mat("socket_off"))
        self.gate.set_actor_location(V(self.gate.get_actor_location().x, self.gate.get_actor_location().y, self.gate_z0), False, False)
        self.gate_solid = True
        self.gate_open_t = -1.0
        self.portal.reset()
        self.portal_on = False
        for pp in self.portal.each("disc"):
            pp.set_mat(self.mat("portal_off"))
        for pp in self.portal.each("beam"):
            pp.a.set_actor_hidden_in_game(True)
        for L, _ in self.portal.lights:
            L.point_light_component.set_intensity(0.0)
        self.state = "play"
        self.time = 0.0
        self.shake = 0.0
        self.msg_t = 0.0
        self.boss_announced = False
        self.grace = START_GRACE
        self.say("EMBER RUINS", "Find the 3 Ember Keys to open the gate", 4.0)
        cx, cy, cz = p.x + CAM_OFFSET[0], p.y + CAM_OFFSET[1], CAM_OFFSET[2]
        self.cam_pos = [cx, cy, cz]
        self.cam.set_actor_location_and_rotation(V(cx, cy, cz), R(0, CAM_PITCH), False, False)
        try:
            self.pc.set_editor_property("show_mouse_cursor", True)
        except Exception:
            pass
        self.pc.set_view_target_with_blend(self.cam, 0.0)
        try:
            self.cam.camera_component.set_field_of_view(CAM_FOV)
        except Exception:
            pass

    # ---------------------------------------------------------------- per-frame
    def update(self, dt):
        if GS.is_game_paused(self.world):
            return
        if self.pc.get_view_target() != self.cam:
            self.pc.set_view_target_with_blend(self.cam, 0.0)
        if self.pressed("R"):
            self.restart()
            return
        if self.state == "play":
            self.time += dt
            self.grace = max(0.0, self.grace - dt)
            self.update_player(dt)
            for e in self.enemies:
                self.update_enemy(e, dt)
            self.separate()
            self.update_orbs(dt)
            self.update_pickups(dt)
            self.update_world(dt)
        else:
            self.update_pickups(dt)
            self.update_world(dt)
        self.animate_player(dt)
        self.update_camera(dt)
        self.update_hud(dt)

    # ---------------------------------------------------------------- player
    def update_player(self, dt):
        p = self.player
        p.inv = max(0.0, p.inv - dt)
        p.dash_cd = max(0.0, p.dash_cd - dt)
        p.atk_cd = max(0.0, p.atk_cd - dt)
        p.aim_mouse = max(0.0, p.aim_mouse - dt)
        ix = (1 if self.down("W", "Up") else 0) - (1 if self.down("S", "Down") else 0)
        iy = (1 if self.down("D", "Right") else 0) - (1 if self.down("A", "Left") else 0)
        il = math.hypot(ix, iy)
        if il > 0:
            ix, iy = ix / il, iy / il

        # aiming: the mouse wins while it is being moved, otherwise face where you walk
        mp = self.pc.get_mouse_position()
        nums = [v for v in (mp if isinstance(mp, (tuple, list)) else ()) if isinstance(v, float)]
        if len(nums) >= 2:
            m = (round(nums[-2]), round(nums[-1]))
            if self.last_mouse is not None and m != self.last_mouse:
                p.aim_mouse = 2.0
            self.last_mouse = m
        aim_yaw = None
        click = self.pressed("LeftMouseButton")
        if p.aim_mouse > 0 or click:
            hit = self.pc.get_hit_result_under_cursor_by_channel(unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False)
            if hit is not None:
                tup = hit.to_tuple()
                if tup[0]:
                    loc = tup[4]
                    if math.hypot(loc.x - p.x, loc.y - p.y) > 20:
                        aim_yaw = math.degrees(math.atan2(loc.y - p.y, loc.x - p.x))
        if aim_yaw is None and il > 0 and p.atk_t <= 0:
            aim_yaw = math.degrees(math.atan2(iy, ix))
        if aim_yaw is not None and p.dash_t <= 0:
            d = (aim_yaw - p.yaw + 180) % 360 - 180
            p.yaw += d * min(1.0, dt * 18)

        # dash
        if self.pressed("LeftShift", "RightShift") and p.dash_cd <= 0 and p.dash_t <= 0:
            if il > 0:
                p.dash_dir = (ix, iy)
            else:
                p.dash_dir = (math.cos(math.radians(p.yaw)), math.sin(math.radians(p.yaw)))
            p.dash_t = DASH_TIME
            p.dash_cd = DASH_CD
        if p.dash_t > 0:
            p.dash_t -= dt
            dx, dy = p.dash_dir[0] * DASH_SPEED * dt, p.dash_dir[1] * DASH_SPEED * dt
        else:
            slow = 0.45 if p.atk_t > 0 else 1.0
            dx, dy = ix * P_SPEED * slow * dt, iy * P_SPEED * slow * dt
        dx += p.kx * dt
        dy += p.ky * dt
        p.kx *= math.exp(-9 * dt)
        p.ky *= math.exp(-9 * dt)
        self.move(p, dx, dy)

        # attack
        if (self.pressed("SpaceBar") or click) and p.atk_cd <= 0 and p.dash_t <= 0:
            if click and aim_yaw is not None:
                p.yaw = aim_yaw
            p.atk_t = ATK_TIME
            p.atk_cd = ATK_CD
            p.swing_dir = -p.swing_dir
            self.do_attack()
        if p.atk_t > 0:
            p.atk_t -= dt
        p.sync()

    def do_attack(self):
        p = self.player
        hit_any = False
        for e in self.enemies:
            if not e.alive or e.dying > 0 or (e.kind == "Warden" and not e.awake):
                continue
            dx, dy = e.x - p.x, e.y - p.y
            dist = math.hypot(dx, dy)
            if dist > ATK_REACH + e.r:
                continue
            if dist > e.r and ang_diff(math.degrees(math.atan2(dy, dx)), p.yaw) > ATK_ARC:
                continue
            self.damage_enemy(e, 1, dx / max(dist, 1), dy / max(dist, 1))
            hit_any = True
        for o in self.orbs:  # swat orbs out of the air
            if o["on"] and math.hypot(o["x"] - p.x, o["y"] - p.y) < ATK_REACH:
                self.kill_orb(o)
        if hit_any:
            self.add_shake(0.25)

    def hurt_player(self, dmg, fx, fy):
        p = self.player
        if p.inv > 0 or p.dash_t > 0 or self.state != "play" or self.god:
            return
        p.hp -= dmg
        p.inv = INVULN
        p.kx, p.ky = fx * 650, fy * 650
        self.add_shake(0.6)
        if p.hp <= 0:
            p.hp = 0
            self.state = "dead"
            self.say("YOU FELL", "Press R to rise again", 9999, (255, 90, 80))

    def animate_player(self, dt):
        p = self.player
        p.t += dt
        if p.atk_t > 0:
            k = 1.0 - p.atk_t / ATK_TIME
            a = lerp(85, -85, k) * p.swing_dir
            sword_mat = self.mat("sword_glow")
        else:
            a = 55.0
            sword_mat = None
        ra = math.radians(a)
        for s in p.each("sword"):
            s.set_rel(V(math.cos(ra) * 88, math.sin(ra) * 88, 78), R(a))
            s.set_mat(sword_mat or s.mat0)
        for s in p.each("hilt"):
            s.set_rel(V(math.cos(ra) * 30, math.sin(ra) * 30, 78), R(a + 90))
        # hurt blink + dash squash
        blink = p.inv > 0 and int(p.inv * 14) % 2 == 0
        body_mat = self.mat("hurt") if blink else None
        for s in p.each("body") + p.each("cape"):
            s.set_mat(body_mat or s.mat0)
        st = 1.0 + (0.25 if p.dash_t > 0 else 0.0)
        for s in p.each("body"):
            s.set_scale(s.scl0.x * st, s.scl0.y / st, s.scl0.z)
        if self.state == "dead":
            for s in p.each("body") + p.each("head") + p.each("helm") + p.each("visor"):
                s.set_mat(self.mat("hurt"))

    # ---------------------------------------------------------------- enemies
    def damage_enemy(self, e, dmg, nx, ny):
        e.hp -= dmg
        e.flash = 0.12
        push = 120 if e.kind == "Warden" else (300 if e.kind == "Brute" else 560)
        e.kx, e.ky = nx * push, ny * push
        e.awake = True
        if e.kind == "Brute" and e.state == "windup":
            e.state, e.st = "stun", 0.5
        self.update_bar(e)
        if e.hp <= 0:
            e.dying = 0.3
            self.add_shake(0.4 if e.kind != "Warden" else 1.2)
            drop = {"Slime": 0.25, "Spitter": 0.35, "Brute": 1.0, "Warden": 0.0}[e.kind]
            if random.random() < drop:
                self.drop_heart(e.x, e.y)

    def update_bar(self, e):
        show = e.alive and (e.hp < KINDS[e.kind][0] or (e.kind == "Warden" and e.awake))
        for b in e.each("bar"):
            frac = max(0.0, e.hp / float(KINDS[e.kind][0]))
            # bars were modelled along X; lay them along Y so they read left-to-right on screen
            b.set_scale(b.scl0.y, max(0.01, b.scl0.x * frac), b.scl0.z)
            b.a.set_actor_hidden_in_game(not show)

    def face(self, e, tx, ty, dt, rate=8.0):
        target = math.degrees(math.atan2(ty - e.y, tx - e.x))
        d = (target - e.yaw + 180) % 360 - 180
        e.yaw += d * min(1.0, dt * rate)

    def update_enemy(self, e, dt):
        if not e.alive:
            return
        e.t += dt
        if e.dying > 0:
            e.dying -= dt
            k = 1.0 + (0.3 - e.dying) * 2.5
            for ps in e.parts.values():
                for s in ps:
                    s.set_scale(s.scl0.x * k, s.scl0.y * k, s.scl0.z * max(0.05, 1.6 - k))
                    s.set_mat(self.mat("flash"))
            if e.dying <= 0:
                e.alive = False
                e.set_hidden(True)
                if e.kind == "Warden":
                    self.open_portal()
            return
        p = self.player
        kind = KINDS[e.kind]
        dx, dy = p.x - e.x, p.y - e.y
        dist = math.hypot(dx, dy) or 1.0
        nx, ny = dx / dist, dy / dist
        if not e.awake and self.grace <= 0 and dist < kind[3] and (e.kind != "Warden" or p.x > 1250):
            e.awake = True
            self.update_bar(e)
            if e.kind == "Warden" and not self.boss_announced:
                self.boss_announced = True
                self.say("THE WARDEN", "Dodge its slam with Shift", 3.0, (255, 120, 60))
        mx = my = 0.0
        speed = kind[2]
        e.cd -= dt
        body_mat = None

        if e.awake and self.state == "play":
            if e.kind == "Slime":
                hop = abs(math.sin(e.t * 5.0))
                mx, my = nx * speed * (0.3 + 0.7 * hop), ny * speed * (0.3 + 0.7 * hop)
                self.face(e, p.x, p.y, dt)
            elif e.kind == "Brute":
                e.st -= dt
                if e.state in ("idle", "chase"):
                    e.state = "chase"
                    mx, my = nx * speed, ny * speed
                    self.face(e, p.x, p.y, dt, 5)
                    if dist < 520 and e.cd <= 0:
                        e.state, e.st, e.lock = "windup", 0.65, (nx, ny)
                elif e.state == "windup":
                    body_mat = self.mat("windup") if int(e.st * 16) % 2 == 0 else None
                    self.face(e, p.x, p.y, dt, 10)
                    e.lock = (math.cos(math.radians(e.yaw)), math.sin(math.radians(e.yaw)))
                    if e.st <= 0:
                        e.state, e.st = "charge", 0.55
                elif e.state == "charge":
                    body_mat = self.mat("windup")
                    if self.move(e, e.lock[0] * 1150 * dt, e.lock[1] * 1150 * dt):
                        e.state, e.st = "stun", 1.3
                        self.add_shake(0.5)
                    elif e.st <= 0:
                        e.state, e.st = "recover", 0.5
                elif e.state == "stun":
                    e.yaw += math.sin(e.t * 30) * 2
                    if e.st <= 0:
                        e.state, e.cd = "chase", 1.4
                elif e.state == "recover":
                    if e.st <= 0:
                        e.state, e.cd = "chase", 1.2
            elif e.kind == "Spitter":
                self.face(e, p.x, p.y, dt, 6)
                if dist < 520:
                    mx, my = -nx * speed, -ny * speed
                elif dist > 820:
                    mx, my = nx * speed, ny * speed
                if random.random() < dt * 0.4:
                    e.strafe = -e.strafe
                mx += -ny * e.strafe * speed * 0.6
                my += nx * e.strafe * speed * 0.6
                if e.cd <= 0.35:
                    for s in e.each("eye"):
                        g = 1.0 + (0.35 - max(e.cd, 0)) * 2.5
                        s.set_scale(s.scl0.x * g, s.scl0.y * g, s.scl0.z * g)
                if e.cd <= 0:
                    for s in e.each("eye"):
                        s.set_scale(s.scl0.x, s.scl0.y, s.scl0.z)
                    self.fire_orb(e.x + nx * 50, e.y + ny * 50, nx, ny, 640)
                    e.cd = 2.0 + random.random() * 0.6
            elif e.kind == "Warden":
                self.update_warden(e, dt, nx, ny, dist)
                body_mat = e.body_mat

        # contact damage
        e.touch_cd = max(0.0, e.touch_cd - dt)
        if e.awake and e.touch_cd <= 0 and dist < e.r + P_RADIUS - 8:
            e.touch_cd = 1.4
            dmg = kind[4] + (1 if (e.kind == "Brute" and e.state == "charge") else 0)
            self.hurt_player(dmg, nx, ny)
            if e.kind != "Warden":  # bounce off so enemies don't sit on top of you
                e.kx, e.ky = -nx * 380, -ny * 380

        mx += e.kx
        my += e.ky
        e.kx *= math.exp(-8 * dt)
        e.ky *= math.exp(-8 * dt)
        if mx or my:
            self.move(e, mx * dt, my * dt)

        # looks: flash, bob, squash
        if e.flash > 0:
            e.flash -= dt
            body_mat = self.mat("flash")
        for s in e.each("body") + e.each("head") + e.each("arm") + e.each("fist"):
            s.set_mat(body_mat or s.mat0)
        if e.kind == "Slime":
            hop = abs(math.sin(e.t * 5.0)) if e.awake else 0.3 * abs(math.sin(e.t * 2))
            for s in e.each("body"):
                s.set_rel(V(s.loc0.x, s.loc0.y, s.loc0.z + hop * 28))
                s.set_scale(s.scl0.x * (1 + 0.12 * (1 - hop)), s.scl0.y * (1 + 0.12 * (1 - hop)), s.scl0.z * (0.85 + 0.25 * hop))
            for s in e.each("eye"):
                s.set_rel(V(s.loc0.x, s.loc0.y, s.loc0.z + hop * 28))
        e.sync()

    def update_warden(self, e, dt, nx, ny, dist):
        e.body_mat = None
        enraged = e.hp <= KINDS["Warden"][0] / 2
        e.st -= dt
        if e.state == "idle":
            e.state, e.st, e.next = "chase", 1.5, "slam"
        if e.state == "chase":
            sp = 210 if enraged else 150
            self.move(e, nx * sp * dt, ny * sp * dt)
            self.face(e, self.player.x, self.player.y, dt, 3)
            if e.st <= 0:
                e.state = e.next + "_windup"
                e.st = 0.8 if e.next == "slam" else 0.55
                e.next = "fan" if e.next == "slam" else "slam"
        elif e.state == "slam_windup":
            e.body_mat = self.mat("windup") if int(e.st * 14) % 2 == 0 else None
            lift = (0.8 - max(e.st, 0)) / 0.8
            e.z = e.z0 + 40 * lift
            if e.st <= 0:
                e.z = e.z0
                e.state, e.st = "chase", (1.6 if enraged else 2.4)
                self.shock_t = 0.0
                self.shock_x, self.shock_y = e.x, e.y
                self.add_shake(1.0)
        elif e.state == "fan_windup":
            e.body_mat = self.mat("windup")
            self.face(e, self.player.x, self.player.y, dt, 6)
            if e.st <= 0:
                n = 9 if enraged else 7
                base = math.atan2(ny, nx)
                for i in range(n):
                    a = base + math.radians(-50 + 100.0 * i / (n - 1))
                    self.fire_orb(e.x + math.cos(a) * 120, e.y + math.sin(a) * 120, math.cos(a), math.sin(a), 560)
                e.state, e.st = "chase", (1.4 if enraged else 2.2)

    def separate(self):
        live = [e for e in self.enemies if e.alive and e.dying <= 0]
        for i in range(len(live)):
            a = live[i]
            for j in range(i + 1, len(live)):
                b = live[j]
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                m = a.r + b.r
                if 0 < d < m:
                    push = (m - d) * 0.5
                    a.x, a.y = self.collide(a.x - dx / d * push, a.y - dy / d * push, a.r)
                    b.x, b.y = self.collide(b.x + dx / d * push, b.y + dy / d * push, b.r)

    # ---------------------------------------------------------------- projectiles
    def fire_orb(self, x, y, nx, ny, speed):
        for o in self.orbs:
            if not o["on"]:
                o.update(on=True, x=x, y=y, vx=nx * speed, vy=ny * speed, life=4.0)
                o["a"].set_actor_hidden_in_game(False)
                o["a"].set_actor_location(V(x, y, 75), False, False)
                return

    def kill_orb(self, o):
        o["on"] = False
        o["a"].set_actor_hidden_in_game(True)
        o["a"].set_actor_location(V(0, 0, -3000), False, False)

    def update_orbs(self, dt):
        p = self.player
        for o in self.orbs:
            if not o["on"]:
                continue
            o["x"] += o["vx"] * dt
            o["y"] += o["vy"] * dt
            o["life"] -= dt
            if o["life"] <= 0 or self.blocked(o["x"], o["y"]):
                self.kill_orb(o)
                continue
            if math.hypot(o["x"] - p.x, o["y"] - p.y) < P_RADIUS + 16:
                d = math.hypot(o["vx"], o["vy"]) or 1
                self.hurt_player(1, o["vx"] / d, o["vy"] / d)
                if p.dash_t <= 0:
                    self.kill_orb(o)
                continue
            o["a"].set_actor_location(V(o["x"], o["y"], 75 + 6 * math.sin(o["life"] * 20)), False, False)
        # warden shockwave ring
        if self.shock_t >= 0:
            self.shock_t += dt
            k = self.shock_t / 0.4
            rad = 40 + 380 * k
            self.shock.set_actor_location(V(self.shock_x, self.shock_y, 8), False, False)
            self.shock.set_actor_scale3d(V(rad / 50, rad / 50, 0.04))
            self.shock.set_actor_hidden_in_game(False)
            dd = math.hypot(p.x - self.shock_x, p.y - self.shock_y)
            if abs(dd - rad) < 70 and self.shock_t < 0.4:
                self.hurt_player(2, (p.x - self.shock_x) / max(dd, 1), (p.y - self.shock_y) / max(dd, 1))
            if self.shock_t >= 0.45:
                self.shock_t = -1.0
                self.shock.set_actor_hidden_in_game(True)
                self.shock.set_actor_location(V(0, 0, -3000), False, False)

    # ---------------------------------------------------------------- pickups / world
    def drop_heart(self, x, y):
        for h in self.drop_hearts:
            if h.taken:
                h.taken = False
                h.x, h.y, h.z = x, y, 4
                h.set_hidden(False)
                h.sync()
                return

    def update_pickups(self, dt):
        p = self.player
        for k in self.keys_ents:
            if k.taken:
                continue
            k.t += dt
            for s in k.each("gem"):
                s.set_rel(V(0, 0, 85 + 12 * math.sin(k.t * 2.5)), R(k.t * 120, 35, 45))
            if self.state == "play" and math.hypot(k.x - p.x, k.y - p.y) < 95:
                k.taken = True
                k.set_hidden(True)
                self.sockets[self.keys_found][1].set_mat(self.mat("gold"))
                self.keys_found += 1
                if self.keys_found < 3:
                    self.say("EMBER KEY %d / 3" % self.keys_found, "The gate stirs...", 2.2)
                else:
                    self.say("THE GATE OPENS", "Face the Warden in the sanctum", 3.0)
                    self.gate_open_t = 0.0
                    self.add_shake(0.8)
        for h in self.hearts + self.drop_hearts:
            if h.taken:
                continue
            h.t += dt
            pulse = 1.0 + 0.12 * math.sin(h.t * 6)
            for s in h.each("lobe") + h.each("tip"):
                s.set_scale(s.scl0.x * pulse, s.scl0.y * pulse, s.scl0.z * pulse)
            h.yaw = (h.t * 90) % 360
            h.sync()
            if self.state == "play" and p.hp < P_MAX_HP and math.hypot(h.x - p.x, h.y - p.y) < 85:
                h.taken = True
                h.set_hidden(True)
                p.hp += 1

    def open_portal(self):
        self.portal_on = True
        for pp in self.portal.each("disc"):
            pp.set_mat(self.mat("portal"))
        for pp in self.portal.each("beam"):
            pp.a.set_actor_hidden_in_game(False)
        for L, _ in self.portal.lights:
            L.point_light_component.set_intensity(80.0)
        self.say("THE WARDEN FALLS", "Step into the portal", 3.0, (120, 230, 255))

    def update_world(self, dt):
        # gate sinks into the floor
        if self.gate_open_t >= 0:
            self.gate_open_t += dt
            k = min(1.0, self.gate_open_t / 1.6)
            gl = self.gate.get_actor_location()
            self.gate.set_actor_location(V(gl.x, gl.y + math.sin(self.gate_open_t * 40) * (1 - k) * 0.0, self.gate_z0 - 340 * k * k), False, False)
            if k > 0.5:
                self.gate_solid = False
            if k >= 1.0:
                self.gate_open_t = -1.0
            self.add_shake(0.15)
        # portal pulse + win check
        self.portal.t += dt
        if self.portal_on:
            for pp in self.portal.each("beam"):
                s = 1.0 + 0.08 * math.sin(self.portal.t * 5)
                pp.set_scale(pp.scl0.x * s, pp.scl0.y * s, pp.scl0.z)
            p = self.player
            if self.state == "play" and math.hypot(p.x - self.portal.x, p.y - self.portal.y) < 130:
                self.state = "won"
                m, s = divmod(int(self.time), 60)
                self.say("VICTORY", "Ruins cleared in %d:%02d  -  press R to play again" % (m, s), 9999, (120, 230, 255))
        # flicker the braziers
        t = self.time + self.portal.t
        for i, (a, l0) in enumerate(self.embers[:16]):
            f = 1.0 + 0.08 * math.sin(t * 9 + i * 1.7) + 0.05 * math.sin(t * 23 + i)
            a.set_actor_scale3d(V(0.5 * f, 0.5 * f, 0.32 * f))

    # ---------------------------------------------------------------- camera / HUD
    def update_camera(self, dt):
        p = self.player
        tx, ty, tz = p.x + CAM_OFFSET[0], p.y + CAM_OFFSET[1], CAM_OFFSET[2]
        k = min(1.0, dt * 6.0)
        c = self.cam_pos
        c[0] += (tx - c[0]) * k
        c[1] += (ty - c[1]) * k
        c[2] += (tz - c[2]) * k
        self.shake = max(0.0, self.shake - dt * 2.5)
        s = self.shake * self.shake * 30
        self.cam.set_actor_location_and_rotation(
            V(c[0] + random.uniform(-s, s), c[1] + random.uniform(-s, s), c[2] + random.uniform(-s, s)),
            R(0, CAM_PITCH), False, False)

    def update_hud(self, dt):
        p = self.player
        if self.msg_t < 9000:
            self.msg_t -= dt
            if self.msg_t <= 0:
                self.title.set_text("")
                self.subtitle.set_text("")
        hearts = "<3 " * p.hp + "-- " * (P_MAX_HP - p.hp)
        self.hud("td_1", "HEALTH   " + hearts, (1.0, 0.35, 0.35))
        self.hud("td_2", "EMBER KEYS   %d / 3" % self.keys_found, (1.0, 0.75, 0.25))
        if self.keys_found < 3:
            goal = "Goal: find the Ember Keys (look for the golden glow)"
        elif self.warden.alive:
            goal = "Goal: defeat the Warden beyond the gate"
        else:
            goal = "Goal: enter the portal"
        self.hud("td_3", goal, (0.85, 0.9, 1.0))
        self.hud("td_4", "WASD move  |  Mouse aim  |  Space / Left Click attack  |  Shift dash  |  R restart", (0.6, 0.6, 0.7))


# ------------------------------------------------------------------ editor hook
_G = None
_fail = 0.0

def _tick(dt):
    global _G, _fail
    try:
        playing = les.is_in_play_in_editor()
    except Exception:
        playing = False
    if not playing:
        if _G is not None:
            _G = None
        _fail = 0.0
        return
    world = ues.get_game_world()
    if world is None:
        return
    if _G is None:
        if _fail > 0:
            _fail -= dt
            return
        try:
            if not GS.get_all_actors_with_tag(world, "TD_Camera"):
                _G = "skip"
                return
            if GS.get_player_controller(world, 0) is None:
                return
            _G = Game(world)
            unreal.log("[td_game] Ember Ruins started")
        except Exception as e:
            import traceback
            traceback.print_exc()
            _G = None
            _fail = 2.0
        return
    if _G == "skip":
        return
    try:
        _G.update(min(dt, 0.05))
    except Exception:
        import traceback
        traceback.print_exc()
        _G = None
        _fail = 2.0


def install():
    uninstall()
    if not hasattr(builtins, "_td_game_handles"):
        builtins._td_game_handles = []
    builtins._td_game_handles.append(unreal.register_slate_post_tick_callback(_tick))
    unreal.log("[td_game] installed - press Play in TD_Arena")


def uninstall():
    for h in list(getattr(builtins, "_td_game_handles", [])):
        try:
            unreal.unregister_slate_post_tick_callback(h)
        except Exception:
            pass
    builtins._td_game_handles = []
