using System;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using Reactor;

namespace AUBridge;

// Settings from the command line (--aub-*). Without --aub-id the plugin stays inert.
public sealed class AubConfig
{
    public int Id;
    public string Mode = "none";
    public string Name;
    public int Color = -1;
    public int Port;
    public string Token;

    public static AubConfig Parse(string[] args)
    {
        var c = new AubConfig();
        bool hasId = false;
        foreach (var a in args)
        {
            if (!a.StartsWith("--aub-", StringComparison.Ordinal)) continue;
            int eq = a.IndexOf('=');
            if (eq < 0) continue;
            string k = a.Substring(6, eq - 6).ToLowerInvariant(), v = a.Substring(eq + 1);
            switch (k)
            {
                case "id": if (int.TryParse(v, out var id) && id >= 1 && id <= 15) { c.Id = id; hasId = true; } break;
                case "mode": if (v == "host" || v == "join" || v == "none") c.Mode = v; break;
                case "name": c.Name = Validate.Name(v); break;
                case "color": if (int.TryParse(v, out var col) && col >= 0 && col <= 17) c.Color = col; break;
                case "port": if (int.TryParse(v, out var p) && p >= 1024 && p <= 65535) c.Port = p; break;
                case "token": if (v.Length > 0) c.Token = v; break;
            }
        }
        if (!hasId) return null;
        if (c.Port == 0) c.Port = 47000 + c.Id;
        return c;
    }
}

public static class Validate
{
    // Max 10 chars (game limit); letters, digits, space and a few safe symbols only.
    public static string Name(string s)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        var sb = new System.Text.StringBuilder();
        foreach (var ch in s.Trim())
        {
            if (sb.Length >= 10) break;
            if (char.IsLetterOrDigit(ch) || ch == ' ' || ch == '_' || ch == '-' || ch == '.') sb.Append(ch);
        }
        var r = sb.ToString().Trim();
        return r.Length == 0 ? null : r;
    }
}

[BepInPlugin(PluginId, "AUBridge", "0.4.0")]
[BepInProcess("Among Us.exe")]
[BepInDependency(ReactorPlugin.Id)]
public class Plugin : BasePlugin
{
    public const string PluginId = "dev.tartaluga.aubridge";
    public static ManualLogSource Logger;
    public static AubConfig Cfg;

    public override void Load()
    {
        Logger = Log;
        Cfg = AubConfig.Parse(Environment.GetCommandLineArgs());
        if (Cfg == null) { Log.LogInfo("[AUB] no --aub-id, plugin inactive"); return; }
        Log.LogInfo($"[AUB] id={Cfg.Id} mode={Cfg.Mode} name={Cfg.Name} color={Cfg.Color} port={Cfg.Port} token={(Cfg.Token != null ? "set" : "none")}");

        var harmony = new Harmony(PluginId);
        harmony.PatchAll(typeof(Patches));
        foreach (var t in new[] { typeof(PMurder), typeof(PStartMeeting), typeof(PChat), typeof(PGameEnd), typeof(PVotingComplete), typeof(PCastVote), typeof(PVentEnter), typeof(PVentExit), typeof(PPhysics), typeof(PJoyKey) })
        {
            try { harmony.CreateClassProcessor(t).Patch(); Log.LogInfo("[AUB] hook ok: " + t.Name); }
            catch (Exception e) { Log.LogWarning($"[AUB] hook {t.Name} failed: {e.Message}"); }
        }
        IL2CPPChainloader.AddUnityComponent(typeof(Runner));
        Bridge.Start(Cfg.Port, Cfg.Token);
    }
}

