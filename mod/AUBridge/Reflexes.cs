using System;
using System.Collections.Generic;
using System.Text.Json;
using UnityEngine;

namespace AUBridge;

public sealed class ReflexDef
{
    public string Type, Target;
    public int MaxWitnesses;
    public float Distance = 4f;
    public int Min = 2;
}

// Reflexes: checked ~10 times per second inside the mod; the agent only switches them on.
// A reflex that needs to move the body takes over the current occupation (an "override") and hands it back when done.
public static partial class Body
{
    static List<ReflexDef> _reflexes = new();
    static readonly string[] ReflexTypes = { "kill_if_alone", "report_on_body", "flee_on_kill_seen", "stick_to_group", "avoid", "self_report" };

    // override (a reflex driving the body)
    static string _ovr; static int _ovrPri; static ActArgs _ovrSaved; static bool _ovrSavedAuto;
    static byte _ovrBodyId; static Vector2 _ovrPos; static float _ovrStart, _ovrRetarget, _ovrLastSeen; static string _ovrTarget;
    static float _rNext, _rKillAt, _belowSince;
    static float _selfReportAt; static byte _selfReportVictim;

    // ---------------- parse / set ----------------
    public static List<ReflexDef> ParseReflexes(JsonElement set)
    {
        if (set.ValueKind != JsonValueKind.Array) throw new BridgeError("'set' must be an array");
        if (set.GetArrayLength() > 12) throw new BridgeError("too many reflexes (max 12)");
        var res = new List<ReflexDef>();
        foreach (var e in set.EnumerateArray())
        {
            if (e.ValueKind != JsonValueKind.Object) throw new BridgeError("reflex must be an object");
            var d = new ReflexDef();
            if (!e.TryGetProperty("type", out var t) || t.ValueKind != JsonValueKind.String) throw new BridgeError("reflex needs 'type'");
            d.Type = t.GetString();
            if (Array.IndexOf(ReflexTypes, d.Type) < 0) throw new BridgeError("unknown reflex type '" + (d.Type.Length > 30 ? d.Type.Substring(0, 30) : d.Type) + "' (" + string.Join("|", ReflexTypes) + ")");
            if (e.TryGetProperty("target", out var tg) && tg.ValueKind != JsonValueKind.Null)
            {
                if (tg.ValueKind != JsonValueKind.String || tg.GetString().Length > 30) throw new BridgeError("bad target");
                d.Target = tg.GetString();
            }
            if (e.TryGetProperty("maxWitnesses", out var mw) && mw.ValueKind != JsonValueKind.Null)
            {
                if (mw.ValueKind != JsonValueKind.Number || !mw.TryGetInt32(out var mwv) || mwv < 0 || mwv > 10) throw new BridgeError("bad maxWitnesses (0..10)");
                d.MaxWitnesses = mwv;
            }
            if (e.TryGetProperty("distance", out var di) && di.ValueKind != JsonValueKind.Null)
            {
                if (di.ValueKind != JsonValueKind.Number || !di.TryGetSingle(out var dv) || float.IsNaN(dv) || dv < 1f || dv > 15f) throw new BridgeError("bad distance (1..15)");
                d.Distance = dv;
            }
            if (e.TryGetProperty("min", out var mn) && mn.ValueKind != JsonValueKind.Null)
            {
                if (mn.ValueKind != JsonValueKind.Number || !mn.TryGetInt32(out var mnv) || mnv < 1 || mnv > 9) throw new BridgeError("bad min (1..9)");
                d.Min = mnv;
            }
            if (d.Type == "avoid" && string.IsNullOrEmpty(d.Target)) throw new BridgeError("avoid needs target");
            foreach (var o in res) if (o.Type == d.Type && (d.Type != "avoid" || string.Equals(o.Target, d.Target, StringComparison.OrdinalIgnoreCase))) throw new BridgeError("duplicate reflex " + d.Type);
            res.Add(d);
        }
        return res;
    }

    static bool PlayerNameExists(string name)
    {
        var all = PlayerControl.AllPlayerControls;
        for (int i = 0; i < all.Count; i++)
            if (all[i] != null && all[i].Data != null && string.Equals(all[i].Data.PlayerName, name, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    public static object SetReflexes(List<ReflexDef> defs)
    {
        if (defs.Count > 0)
        {
            if (!Game.ShipUp || !Game.Started) throw new BridgeError("not in a running game");
            var me = Me;
            foreach (var d in defs)
            {
                if ((d.Type == "kill_if_alone" || d.Type == "self_report") && !Game.AmImpostor(me)) throw new BridgeError(d.Type + " is only for impostors");
                if (!string.IsNullOrEmpty(d.Target) && !string.Equals(d.Target, "any", StringComparison.OrdinalIgnoreCase) && !PlayerNameExists(d.Target)) throw new BridgeError("unknown player '" + d.Target + "'");
            }
        }
        _reflexes = defs;
        if (_ovr != null && !HasReflexFor(_ovr)) EndOverride();
        _belowSince = 0;
        Plugin.Logger.LogInfo("[AUB] reflexes set: " + defs.Count);
        return null;
    }

    static bool HasReflexFor(string ovr)
    {
        string t = ovr == "r_report" ? "report_on_body" : ovr == "r_flee" ? "flee_on_kill_seen" : ovr == "r_group" ? "stick_to_group" : "avoid";
        foreach (var d in _reflexes) if (d.Type == t) return true;
        return false;
    }

    static ReflexDef Find(string type) { foreach (var d in _reflexes) if (d.Type == type) return d; return null; }

    public static List<object> ReflexInfo()
    {
        var res = new List<object>();
        foreach (var d in _reflexes)
        {
            var o = new Dictionary<string, object> { ["type"] = d.Type };
            if (d.Type == "kill_if_alone") { o["target"] = d.Target ?? "any"; o["maxWitnesses"] = d.MaxWitnesses; }
            if (d.Type == "avoid") { o["target"] = d.Target; o["distance"] = d.Distance; }
            if (d.Type == "stick_to_group") o["min"] = d.Min;
            res.Add(o);
        }
        return res;
    }

    static void Fire(string type, string detail)
    {
        Events.Add("reflex_fired", "reflex", type, "detail", detail);
    }

    // ---------------- override machinery ----------------
    static void ClearOverride() { _ovr = null; _ovrSaved = null; _ovrPri = 0; }

    static bool BeginOverride(string kind, int pri)
    {
        if (_ovr != null)
        {
            if (_ovr != kind && _ovrPri >= pri) return false;
            if (_ovr == kind) return true;
            StopCore(); ReleaseFix();
            _kind = kind; _ovr = kind; _ovrPri = pri; Active = true; _ovrStart = Events.Now;
            return true;
        }
        _ovrSavedAuto = _auto;
        _ovrSaved = (_kind == null || _kind.StartsWith("r_")) ? null : _lastArgs;
        if (_kind == "stay" && _lastArgs == null) _ovrSaved = StayArgs;
        Stop(); _auto = false;
        _kind = kind; _ovr = kind; _ovrPri = pri; Active = true; _ovrStart = Events.Now;
        return true;
    }

    static void EndOverride()
    {
        var sv = _ovrSaved; var sa = _ovrSavedAuto;
        ClearOverride();
        Stop();
        if (sv != null)
        {
            try { Act(sv); }
            catch (BridgeError) { _kind = "stay"; Active = true; }
        }
        else if (sa) { _auto = true; Active = true; _kind = null; }
        else { _kind = "stay"; Active = true; }
        Desired = Vector2.zero;
    }

    static bool SetGoal(Vector2 pos, Vector2 g)
    {
        _goal = g; _hasGoal = true;
        return Replan(pos);
    }

    // ---------------- hooks from Game ----------------
    static readonly HashSet<byte> _myVictims = new();
    public static void ResetVictims() { _myVictims.Clear(); }
    public static void OnKilled(PlayerControl victim)
    {
        _myVictims.Add(victim.PlayerId);
        if (Find("self_report") != null) { _selfReportAt = Events.Now + 0.3f; _selfReportVictim = victim.PlayerId; }
    }

    public static void OnSawKill(string killer, string victim)
    {
        var d = Find("flee_on_kill_seen");
        var me = Me;
        if (d == null || me == null || me.Data == null || me.Data.IsDead || !Game.ShipUp || !Nav.Ready || Game.InMeetingOrExile) return;
        var pos = me.GetTruePosition();
        var others = new List<Game.PInfo>();
        foreach (var v in Game.Visible(me, pos, Game.LightRadius(me)))
            if (v.Alive && !string.Equals(v.Name, killer, StringComparison.OrdinalIgnoreCase) && !string.Equals(v.Name, victim, StringComparison.OrdinalIgnoreCase)) others.Add(v);
        Vector2 goal; string where;
        if (others.Count >= 2)
        {
            others.Sort((x, y) => x.Dist.CompareTo(y.Dist));
            goal = others[0].Pos; where = "group near " + others[0].Name;
        }
        else if (Nav.RoomGoal("Cafeteria", out goal)) where = "Cafeteria";
        else return;
        if (!BeginOverride("r_flee", 4)) return;
        if (!SetGoal(pos, goal)) { EndOverride(); return; }
        Fire("flee_on_kill_seen", $"saw {killer} kill {victim}, running to {where}");
    }

    // ---------------- per-frame (decisions at 10 Hz) ----------------
    static void ReflexUpdate(PlayerControl me, float now)
    {
        if (_reflexes.Count == 0 && _ovr == null && _selfReportAt == 0) return;
        if (me.Data == null || me.Data.IsDead) { if (_ovr != null) { ClearOverride(); StopCore(); _kind = "stay"; Active = true; } _selfReportAt = 0; return; }
        if (now < _rNext) return;
        _rNext = now + 0.1f;
        var pos = me.GetTruePosition();
        float rad = Game.LightRadius(me);
        bool imp = Game.AmImpostor(me);
        string partner = imp ? Game.Partner(me) : null;
        var vis = new List<Game.PInfo>();
        foreach (var v in Game.Visible(me, pos, rad)) if (v.Alive) vis.Add(v);
        var bodies = Game.Bodies(me, pos, rad);
        var reportable = new List<Game.BInfo>();
        foreach (var b in bodies) if (!_myVictims.Contains(b.Id)) reportable.Add(b); // report_on_body never fires on our own kills (that is self_report)

        // self_report: our own victim, right after the kill
        if (_selfReportAt > 0 && now >= _selfReportAt)
        {
            Game.BInfo mine = null;
            foreach (var b in bodies) if (b.Id == _selfReportVictim) { mine = b; break; }
            if (mine != null && mine.Dist <= me.MaxReportDistance * 0.95f)
            {
                _selfReportAt = 0;
                try { ReportBody(me, mine); Fire("self_report", "reported own victim " + mine.Name); } catch (BridgeError e) { Plugin.Logger.LogWarning("[AUB] self_report: " + e.Message); }
            }
            else if (now > _selfReportAt + 3f) _selfReportAt = 0;
        }

        // kill_if_alone
        var kd = Find("kill_if_alone");
        if (kd != null && imp && !me.inVent && me.killTimer <= 0.05f && now >= _rKillAt)
        {
            float range = KillRange();
            Game.PInfo pick = null; int pw = 0;
            foreach (var c in vis)
            {
                if (c.Dist > range || string.Equals(c.Name, partner, StringComparison.OrdinalIgnoreCase)) continue;
                if (!string.IsNullOrEmpty(kd.Target) && !string.Equals(kd.Target, "any", StringComparison.OrdinalIgnoreCase) && !string.Equals(kd.Target, c.Name, StringComparison.OrdinalIgnoreCase)) continue;
                int w = 0;
                foreach (var o in vis) if (o.Id != c.Id && !string.Equals(o.Name, partner, StringComparison.OrdinalIgnoreCase)) w++;
                if (w <= kd.MaxWitnesses && (pick == null || c.Dist < pick.Dist)) { pick = c; pw = w; }
            }
            if (pick != null)
            {
                try { DoKill(me, pick); _rKillAt = now + 1.5f; Fire("kill_if_alone", $"kill {pick.Name}, witnesses {pw}"); }
                catch (BridgeError e) { Plugin.Logger.LogWarning("[AUB] kill_if_alone: " + e.Message); }
            }
        }

        // report_on_body
        if (Find("report_on_body") != null && !me.inVent && reportable.Count > 0)
        {
            Game.BInfo nb = null;
            foreach (var b in reportable) if (nb == null || b.Dist < nb.Dist) nb = b;
            if (nb.Dist <= me.MaxReportDistance * 0.9f)
            {
                try { ReportBody(me, nb); Fire("report_on_body", "reported " + nb.Name); } catch (BridgeError e) { Plugin.Logger.LogWarning("[AUB] report_on_body: " + e.Message); }
                return;
            }
            if (_ovr != "r_report" && BeginOverride("r_report", 3))
            {
                _ovrBodyId = nb.Id; _ovrPos = nb.Pos;
                if (SetGoal(pos, nb.Pos)) Fire("report_on_body", $"walking to the body of {nb.Name} in {nb.Room ?? "hallway"}");
                else EndOverride();
            }
        }

        // avoid
        foreach (var d in _reflexes)
        {
            if (d.Type != "avoid") continue;
            Game.PInfo t = null;
            foreach (var v in vis) if (string.Equals(v.Name, d.Target, StringComparison.OrdinalIgnoreCase)) { t = v; break; }
            if (_ovr == "r_avoid" && string.Equals(_ovrTarget, d.Target, StringComparison.OrdinalIgnoreCase))
            {
                if (t != null) _ovrLastSeen = now;
                if ((t == null && now - _ovrLastSeen > 1.0f) || (t != null && t.Dist >= d.Distance + 1.5f)) { EndOverride(); continue; }
                if (t != null && now >= _ovrRetarget) { _ovrRetarget = now + 0.6f; AvoidGoal(pos, t.Pos); }
            }
            else if (t != null && t.Dist < d.Distance && _ovr == null || (t != null && t.Dist < d.Distance && _ovr != null && _ovrPri < 2))
            {
                if (BeginOverride("r_avoid", 2))
                {
                    _ovrTarget = d.Target; _ovrLastSeen = now; _ovrRetarget = now + 0.6f;
                    if (AvoidGoal(pos, t.Pos)) Fire("avoid", $"{t.Name} is {t.Dist:0.0} away, backing off");
                    else EndOverride();
                }
            }
        }

        // stick_to_group
        var gd = Find("stick_to_group");
        if (gd != null)
        {
            if (vis.Count < gd.Min)
            {
                if (_belowSince == 0) _belowSince = now;
                if (now - _belowSince >= 1.0f)
                {
                    bool atTask = !(_kind == null || _kind == "stay" || _kind == "wander" || _kind == "r_group"); // only idle/wander may be pulled to a group: never walking to a task console, doing one, moving to a goal or fixing
                    if (!atTask && (_ovr == null || _ovr == "r_group" || _ovrPri < 1))
                    {
                        bool fresh = _ovr != "r_group";
                        if (fresh || now >= _ovrRetarget)
                        {
                            Game.PInfo near = null;
                            foreach (var v in vis) if (near == null || v.Dist < near.Dist) near = v;
                            Vector2 g; string where;
                            if (near != null) { g = near.Pos; where = near.Name; }
                            else if (Nav.RoomGoal("Cafeteria", out g)) where = "Cafeteria";
                            else g = pos + Vector2.zero;
                            where = near != null ? near.Name : "Cafeteria";
                            if (!BeginOverride("r_group", 1)) { /* a stronger reflex is driving */ }
                            else
                            {
                                _ovrRetarget = now + 0.6f;
                                if (SetGoal(pos, g)) { if (fresh) Fire("stick_to_group", $"only {vis.Count} in sight, joining {where}"); }
                                else if (fresh) EndOverride();
                            }
                        }
                    }
                }
            }
            else
            {
                _belowSince = 0;
                if (_ovr == "r_group" && now - _ovrStart >= 1.5f) EndOverride();
            }
        }
        else if (_ovr == "r_group") EndOverride();
    }

    // a point away from the threat that we can reach on foot
    static bool AvoidGoal(Vector2 pos, Vector2 threat)
    {
        Vector2 best = pos; float bd = Vector2.Distance(pos, threat) + 0.01f; bool found = false;
        for (int k = 0; k < 16; k++)
        {
            float ang = k * Mathf.PI / 8f;
            var dir = new Vector2(Mathf.Cos(ang), Mathf.Sin(ang));
            for (float r = 6f; r >= 2.5f; r -= 1.5f)
            {
                var p = pos + dir * r;
                if (!Nav.WalkAt(p) || !Nav.Los(pos, p)) continue;
                float d = Vector2.Distance(p, threat);
                if (d > bd) { bd = d; best = p; found = true; }
                break;
            }
        }
        if (!found) return false;
        return SetGoal(pos, best);
    }

    // drives the body while an override is active
    static void OvrUpdate(PlayerControl me, Vector2 pos, float now)
    {
        switch (_ovr)
        {
            case "r_report":
                {
                    if (now - _ovrStart > 40f) { EndOverride(); return; }
                    if (Vector2.Distance(pos, _ovrPos) <= me.MaxReportDistance * 0.8f)
                    {
                        Game.BInfo hit = null;
                        foreach (var b in Game.Bodies(me, pos, Game.LightRadius(me))) if (b.Id == _ovrBodyId) { hit = b; break; }
                        if (hit != null && hit.Dist <= me.MaxReportDistance * 0.95f)
                        {
                            try { ReportBody(me, hit); Fire("report_on_body", "reported " + hit.Name); } catch (BridgeError e) { Plugin.Logger.LogWarning("[AUB] report: " + e.Message); }
                        }
                        EndOverride();
                        return;
                    }
                    int r = Drive(pos, now);
                    if (r != 0) EndOverride();
                    return;
                }
            case "r_flee":
                {
                    if (now - _ovrStart > 15f) { EndOverride(); return; }
                    int r = Drive(pos, now);
                    if (r != 0) EndOverride();
                    return;
                }
            case "r_group":
            case "r_avoid":
                {
                    int r = Drive(pos, now);
                    if (r == 1) { Desired = Vector2.zero; }
                    else if (r == 2) { _stuckN = 0; _path = null; Desired = Vector2.zero; }
                    return;
                }
        }
    }
}
