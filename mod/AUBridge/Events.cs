using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace AUBridge;

// Thread-safe ring buffer of game events (last 500). Producers: main thread. Consumers: socket threads (wait_event).
public static class Events
{
    const int Cap = 500;
    static readonly object L = new();
    static readonly List<Dictionary<string, object>> Buf = new();
    static long _seq;
    public static float T0; // Time.realtimeSinceStartup at game start

    public static float Now => UnityEngine.Time.realtimeSinceStartup;
    public static double T => Math.Round(Math.Max(0, Now - T0), 2);

    public static void Add(string type, params object[] kv)
    {
        var e = new Dictionary<string, object>();
        long seq;
        lock (L)
        {
            seq = ++_seq;
            e["seq"] = seq; e["t"] = T; e["type"] = type;
            for (int i = 0; i + 1 < kv.Length; i += 2) e[(string)kv[i]] = kv[i + 1];
            Buf.Add(e);
            if (Buf.Count > Cap) Buf.RemoveRange(0, Buf.Count - Cap);
            Monitor.PulseAll(L);
        }
        GameLog.Write(new Dictionary<string, object>(e));
        Plugin.Logger.LogInfo("[AUB] event " + type);
    }

    // Returns events with seq > since; blocks up to timeoutSec while there are none.
    public static (long seq, List<Dictionary<string, object>> events) Wait(long since, double timeoutSec)
    {
        var end = DateTime.UtcNow.AddSeconds(timeoutSec);
        lock (L)
        {
            while (true)
            {
                var res = new List<Dictionary<string, object>>();
                foreach (var e in Buf) if ((long)e["seq"] > since) res.Add(e);
                if (res.Count > 0) return (_seq, res);
                var left = end - DateTime.UtcNow;
                if (left <= TimeSpan.Zero) return (_seq, res);
                Monitor.Wait(L, left);
            }
        }
    }
}

// Per-copy match log: D:\AmongUs-tools\games\<gameId>\p<id>.jsonl (+ god.jsonl on the host). Post-game material only; never served.
public static class GameLog
{
    const string Root = @"D:\AmongUs-tools\games";
    static readonly object L = new();
    static StreamWriter _w, _god;
    public static string Dir;

    public static void Open(string gameId)
    {
        lock (L)
        {
            CloseLocked();
            try
            {
                Dir = Path.Combine(Root, gameId);
                Directory.CreateDirectory(Dir);
                _w = OpenFile(Path.Combine(Dir, $"p{Plugin.Cfg.Id}.jsonl"));
                if (Plugin.Cfg.Mode == "host") _god = OpenFile(Path.Combine(Dir, "god.jsonl"));
                Plugin.Logger.LogInfo("[AUB] game log: " + Dir);
            }
            catch (Exception e) { Plugin.Logger.LogWarning("[AUB] game log disabled: " + e.Message); _w = null; _god = null; }
        }
    }

    static StreamWriter OpenFile(string path)
    {
        if (File.Exists(path)) File.Move(path, path + "." + DateTime.UtcNow.Ticks + ".bak"); // never mix two games in one file
        return new StreamWriter(new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false)) { AutoFlush = true };
    }

    public static void Write(Dictionary<string, object> o) => WriteTo(false, o);
    public static void God(Dictionary<string, object> o) => WriteTo(true, o);

    static void WriteTo(bool god, Dictionary<string, object> o)
    {
        lock (L)
        {
            var w = god ? _god : _w;
            if (w == null) return;
            try
            {
                o["ts"] = DateTime.UtcNow.ToString("HH:mm:ss.fff");
                w.WriteLine(JsonSerializer.Serialize(o));
            }
            catch (Exception) { /* disk problem must never hurt the game */ }
        }
    }

    public static void Close() { lock (L) CloseLocked(); }
    static void CloseLocked()
    {
        try { _w?.Dispose(); _god?.Dispose(); } catch { }
        _w = null; _god = null;
    }
}
