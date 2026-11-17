"""Hexbound audio, synthesized from scratch (no samples, no third-party audio). Gothic witch theme.

Writes web-sdk/apps/hexbound/static/assets/audio/hb/sounds.{ogg,m4a,mp3} + sounds.json: an audio sprite with
the same 52 names the game plays (read from Hexbound's old gb/sounds.json). Glitch Bandit's audio is untouched.

Music (epic, drum-driven): "The Witch's Tower" (base, D minor 88 BPM: taiko ostinato, brass, organ, choir, music box),
"The Witching Hour" (bonus, D minor 112 BPM: driving taiko, brass ostinato, choir), five win loops (one key up per tier).
SFX: stone thuds, bells and chimes, witch-fire whooshes, potion glass and bubbles, wind, gong.
Run: python tools/make_hexbound_sounds.py   (system Python: needs numpy, scipy, ffmpeg on PATH)
"""
import json
import os
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from make_sounds import (SR, Song, bell, bp, expdec, fit, hp, lp, mtof, mx, noise, norm_peak, ns, place, reverb, saw,
                         seq, sine, stereo_place, sweep_lp)

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "web-sdk", "apps", "hexbound")
NAMES_JSON = os.path.join(APP, "static", "assets", "audio", "gb", "sounds.json")  # the 52 names the game plays
OUT = os.path.join(APP, "static", "assets", "audio", "hb")
rng = np.random.default_rng(1692)


# ---------------------------------------------------------------- voices
def organ(ms, d, drawbars=(1.0, 0.6, 0.35, 0.2), trem=4.8):
    """Pipe organ chord: additive sines (8', 4', 2 2/3', 2'), slow attack, gentle tremulant."""
    n = ns(d)
    tt = np.arange(n) / SR
    out = np.zeros(n)
    for m in ms:
        f = float(mtof(m))
        for k, (mul, g) in enumerate(zip((1, 2, 3, 4), drawbars)):
            out += sine(f * mul, n) * g
    a = np.minimum(1, tt / 0.08)
    r = np.minimum(1, (d - tt) / 0.25).clip(0, 1)
    return out / len(ms) * a * r * (1 + 0.06 * np.sin(2 * np.pi * trem * tt))


def harpsichord(m, d):
    """Plucked string: bright saw, fast decay, a little body resonance."""
    n = ns(d)
    f = float(mtof(m))
    x = (saw(f, n) * 0.6 + saw(f * 2.0, n) * 0.25) * expdec(n, 9)
    return hp(lp(x, 5200), 180) * (1 - np.exp(-np.arange(n) / (SR * 0.002)))


def music_box(m, d):
    return bell(m, d, 1.4) * 0.8 + sine(float(mtof(m)) * 4, ns(d)) * expdec(ns(d), 14) * 0.15


def choir(ms, d, vowel="ah"):
    """Wordless choir: detuned saws through vowel formants, slow swell, vibrato."""
    n = ns(d)
    tt = np.arange(n) / SR
    formants = {"ah": ((700, 1100), (1150, 1500), (2500, 3000)), "oo": ((280, 420), (700, 950), (2200, 2600))}[vowel]
    src = np.zeros(n)
    for m in ms:
        for det in (-0.007, 0.0, 0.006):
            f = float(mtof(m)) * (1 + det) * (1 + 0.004 * np.sin(2 * np.pi * 5.2 * tt + det * 900))
            src += saw(f, n)
    v = sum(bp(src, lo, hi) * g for (lo, hi), g in zip(formants, (1.0, 0.6, 0.25)))
    swell = np.minimum(1, tt / 0.6) * np.minimum(1, (d - tt) / 0.5).clip(0, 1)
    return v / (3 * len(ms)) * swell


def toll(m, d=3.0):
    """Big church bell: low inharmonic partials, long ring."""
    n = ns(d)
    f = float(mtof(m))
    parts = ((0.5, 0.5, 1.2), (1.0, 1.0, 1.6), (1.19, 0.6, 2.2), (1.5, 0.45, 2.6), (2.0, 0.35, 3.0), (2.74, 0.2, 4.0))
    return sum(sine(f * mul, n) * g * expdec(n, r) for mul, g, r in parts) * 0.5


def frame_drum(f0=90, d=0.5, g=1.0):
    n = ns(d)
    body = sine(f0 * (0.7 + 0.3 * expdec(n, 18)), n) * expdec(n, 7)
    slap = bp(noise(n), 300, 1800) * expdec(n, 60) * 0.35
    return (body + slap) * g


def war_drum(d=0.7):
    return np.tanh(frame_drum(62, d, 1.6) * 1.3)


def whoosh(d, f0=300, f1=4000, rise=True):
    n = ns(d)
    q = np.linspace(0, 1, n)
    curve = q if rise else 1 - q
    shape = np.sin(np.pi * q) ** 1.5
    return sweep_lp(noise(n), lambda p: f0 + (f1 - f0) * (p if rise else 1 - p)) * shape * (0.4 + 0.6 * curve)


def wind(d, f=500):
    n = ns(d)
    q = np.arange(n) / SR
    return bp(noise(n), f * 0.6, f * 1.6) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.3 * q))


def bubble(f0=500, d=0.12):
    n = ns(d)
    f = f0 * (1 + 2.5 * np.linspace(0, 1, n) ** 2)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * expdec(n, 25)


def glass(m, d=0.6):
    n = ns(d)
    f = float(mtof(m))
    return (sine(f, n) + sine(f * 2.76, n) * 0.4 + sine(f * 5.4, n) * 0.15) * expdec(n, 9)


def gong(d=4.0, f0=70):
    n = ns(d)
    tt = np.arange(n) / SR
    out = np.zeros(n)
    for mul, g in ((1, 1), (1.47, 0.6), (2.09, 0.5), (2.56, 0.35), (3.3, 0.25), (4.2, 0.15)):
        out += sine(f0 * mul * (1 + 0.002 * np.sin(2 * np.pi * 0.7 * tt)), n) * g
    swell = np.minimum(1, tt / 0.02) * expdec(n, 1.1)
    return np.tanh(out * swell * 0.7 + bp(noise(n), 800, 5000) * expdec(n, 6) * 0.1)


def coin(m):
    return bell(m, 0.45, 1.6) * 0.9


# ---------------------------------------------------------------- epic percussion + brass
def taiko(d=0.9, f0=55, g=1.0):
    """Big war drum: deep pitched boom, skin slap, long body."""
    n = ns(d)
    body = sine(f0 * (0.6 + 0.4 * expdec(n, 14)), n) * expdec(n, 4.5)
    sub = sine(f0 * 0.5, n) * expdec(n, 3.0) * 0.6
    slap = bp(noise(n), 200, 2500) * expdec(n, 45) * 0.5
    return np.tanh((body + sub + slap) * 1.8) * g


def tom(f0=110, d=0.45, g=1.0):
    n = ns(d)
    return np.tanh((sine(f0 * (0.65 + 0.35 * expdec(n, 20)), n) * expdec(n, 8) + bp(noise(n), 400, 3000) * expdec(n, 50) * 0.3) * 1.5) * g


def rim(g=1.0):
    n = ns(0.12)
    return (bp(noise(n), 1800, 6000) * expdec(n, 60) + sine(820, n) * expdec(n, 70) * 0.4) * g


def cymbal_swell(d=1.5):
    """Reverse cymbal: bright noise swelling up into the downbeat."""
    n = ns(d)
    q = np.linspace(0, 1, n)
    return hp(noise(n), 4000) * q ** 3


def brass(ms, d, swell=0.12, bright=2200):
    """Low horn section: detuned saws, lowpass that opens with the swell."""
    n = ns(d)
    tt = np.arange(n) / SR
    src = np.zeros(n)
    for m in ms:
        for det in (-0.004, 0.0, 0.005):
            src += saw(float(mtof(m)) * (1 + det), n)
    env_ = np.minimum(1, tt / swell) * np.minimum(1, (d - tt) / 0.2).clip(0, 1)
    x = sweep_lp(src, lambda q: 500 + bright * min(1.0, q * 4))
    return x / (3 * len(ms)) * env_


# taiko ostinato, one bar of 16ths: 2 = heavy hit, 1 = light hit
TAIKO_GROOVE = [2, 0, 0, 1, 2, 0, 1, 0, 2, 0, 0, 1, 2, 1, 1, 1]
TAIKO_DRIVE = [2, 0, 1, 0, 2, 1, 1, 0, 2, 0, 1, 0, 2, 1, 2, 1]


def drums_bar(s, bar, pattern, heavy=1.0):
    for k, hit in enumerate(pattern):
        if hit == 2:
            place(s.drums, taiko(0.9, 52, 0.95 * heavy), s.t(bar, k * 0.25))
        elif hit == 1:
            place(s.drums, tom(120 + 20 * (k % 3), 0.35, 0.45 * heavy), s.t(bar, k * 0.25))
    place(s.drums, rim(0.35), s.t(bar, 1))
    place(s.drums, rim(0.35), s.t(bar, 3))


def tom_fill(s, bar, beats=2.0):
    """Descending tom roll over the last `beats` of the bar, into the next downbeat."""
    steps = int(beats * 4)
    for k in range(steps):
        place(s.drums, tom(220 - 12 * k, 0.4, 0.55 + 0.04 * k), s.t(bar, 4 - beats + k * 0.25))
    place(s.drums, cymbal_swell(s.beat * beats) * 0.35, s.t(bar, 4 - beats))


# ---------------------------------------------------------------- music
CHORDS_DM = [(50, 53, 57), (46, 50, 53), (43, 46, 50), (45, 49, 52)]  # Dm Bb Gm A


def witchs_tower():
    """Base game: D minor, 88 BPM, 16 bars, epic. Bars 0-3 build (organ, harpsichord, single taiko hits),
    4-15 full: taiko ostinato, brass on every chord, choir from bar 8, music box melody on top, gong per section."""
    s = Song(88, 16, tail=4.0)
    melody = [(0, 0, 2, 74), (0, 2, 1, 72), (0, 3, 1, 69), (1, 0, 3, 70), (1, 3, 1, 69),
              (2, 0, 1.5, 67), (2, 1.5, 0.5, 69), (2, 2, 2, 70), (3, 0, 2, 69), (3, 2, 2, 73)]
    arp = [0, 1, 2, 1, 0, 2, 1, 2]
    for bar in range(16):
        c = CHORDS_DM[bar % 4]
        place(s.synth, organ([m + 12 for m in c] + [c[0]], s.bar * 1.05) * 0.24, s.t(bar))
        for k in range(8):
            m = c[arp[k]] + 12 + (12 if k >= 4 else 0)
            stereo_place(s, harpsichord(m, s.beat * 0.9) * 0.12, s.t(bar, k * 0.5), -0.4 if k % 2 else 0.4)
        if bar < 4:
            place(s.drums, taiko(1.2, 50, 0.9), s.t(bar, 0))
            place(s.drums, taiko(1.0, 55, 0.5), s.t(bar, 2.5))
            if bar == 3:
                tom_fill(s, bar, 2.0)
        else:
            drums_bar(s, bar, TAIKO_GROOVE)
            place(s.synth, brass([c[0] - 12, c[0], c[2]], s.bar * 0.95) * 0.32, s.t(bar))
            if bar % 4 == 3:
                tom_fill(s, bar, 1.0)
        if bar in (4, 12):
            place(s.drums, gong(4.0, 58) * 0.6, s.t(bar))
        if bar >= 8:
            place(s.synth, choir([m + 12 for m in c], s.bar * 1.05) * 0.3, s.t(bar))
            for pb, beat, beats, m in melody:
                if pb == bar % 4:
                    stereo_place(s, music_box(m + 12, s.beat * beats + 0.6) * 0.2, s.t(bar, beat), 0.1,
                                 delay_t=s.beat * 0.75, fb=0.25)
    return s.mixdown(rms=0.17, duck=0.0, rev=2.4, pad_send=0.4)


def witching_hour():
    """Bonus: D minor, 112 BPM, 16 bars, relentless: driving taiko every bar, brass ostinato on eighths,
    choir, organ, fast harpsichord, tom fills into every phrase, gong every 4 bars."""
    s = Song(112, 16, tail=3.0)
    for bar in range(16):
        c = CHORDS_DM[bar % 4]
        place(s.synth, choir([m + 12 for m in c], s.bar * 1.05, "ah" if bar % 8 < 4 else "oo") * 0.38, s.t(bar))
        place(s.synth, organ([c[0] - 12, c[0]], s.bar * 1.0, (1.0, 0.5, 0.2, 0.1)) * 0.2, s.t(bar))
        for k in range(8):  # brass ostinato: root-root-fifth-root on eighths
            m = [c[0], c[0], c[2], c[0], c[0], c[2], c[1], c[2]][k] - 12
            place(s.synth, brass([m, m + 12], s.beat * 0.45, swell=0.02, bright=2600) * 0.26, s.t(bar, k * 0.5))
        for k in range(16):
            m = c[k % 3] + 24 + (12 if (k // 4) % 2 else 0)
            stereo_place(s, harpsichord(m, s.beat * 0.4) * 0.08, s.t(bar, k * 0.25), 0.5 if k % 2 else -0.5)
        drums_bar(s, bar, TAIKO_DRIVE, 1.1)
        if bar % 4 == 3:
            tom_fill(s, bar, 1.5)
        if bar % 4 == 0:
            place(s.drums, gong(3.5, 58) * 0.55, s.t(bar))
    return s.mixdown(rms=0.18, duck=0.0, rev=2.0, pad_send=0.35)


def win_loop(key):
    """Win celebration in `key` (midi of I): I-V-vi-IV, 112 BPM, 4 bars: brass fanfare, choir, taiko drive."""
    s = Song(112, 4, tail=2.5)
    prog = [(0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12)]
    for bar in range(4):
        c = [key + i for i in prog[bar]]
        place(s.synth, brass([c[0] - 12] + c, s.bar * 0.98, swell=0.06, bright=3000) * 0.34, s.t(bar))
        place(s.synth, choir([m + 12 for m in c], s.bar * 1.02) * 0.28, s.t(bar))
        for k in range(16):
            m = c[k % 3] + 12 + (12 if (k // 3) % 2 else 0)
            stereo_place(s, harpsichord(m, s.beat * 0.4) * 0.1, s.t(bar, k * 0.25), 0.5 if k % 2 else -0.5)
        drums_bar(s, bar, TAIKO_DRIVE, 1.1)
        for k in range(4):
            stereo_place(s, coin(c[k % 3] + 24) * 0.09, s.t(bar, k + 0.5), 0.6 * (-1) ** k)
    tom_fill(s, 3, 1.0)
    place(s.drums, gong(3.0, 60) * 0.5, 0)
    return s.mixdown(rms=0.18, duck=0.0, rev=1.8, pad_send=0.35)


# ---------------------------------------------------------------- SFX (mono, seconds)
def sfx():
    S = {}
    S["sfx_btn_general"] = fit(glass(96, 0.08) * 0.6, 0.08)
    sp = mx(whoosh(0.45, 250, 3500) * 0.6, glass(88, 0.4) * 0.15)
    S["sfx_btn_spin"] = fit(sp + reverb(sp, 0.8) * 0.3, 1.0)
    for i in range(1, 6):  # reel stops: stone thud, a touch higher per reel
        n = ns(0.22)
        th = sine(70 + 8 * i, n) * expdec(n, 20) + lp(noise(n), 900 + 120 * i) * expdec(n, 45) * 0.45
        S[f"sfx_reel_stop_{i}"] = fit(th, 0.24)
    S["sfx_symbols_landing"] = fit(lp(noise(ns(0.12)), 1400) * expdec(ns(0.12), 35) * 0.5, 1.2)
    S["sfx_royals_landing"] = fit(glass(86, 0.8) * 0.45, 1.2)
    # scatter (full moon) lands: a deep bell and rising chimes, bigger with every moon
    for i in range(1, 6):
        x = mx(toll(50 + 2 * i, 1.4) * 0.5, seq([81 + 2 * i, 88 + 2 * i], 0.08, 0.8, lambda m, d: bell(m, d, 1.2)) * 0.4)
        S[f"sfx_scatter_stop_{i}"] = fit(x * 0.6 + reverb(x, 1.6, i) * 0.3, [0.99, 1.34, 1.06, 1.0, 1.0][i - 1])
    S["sfx_scatter_reveal"] = fit(seq([74, 81, 86, 93], 0.09, 0.8, lambda m, d: bell(m, d)) * 0.5, 1.49)
    sw = mx(choir((62, 69, 74), 1.9) * 0.6, seq([74, 78, 81, 86, 90, 93], 0.08, 0.6, lambda m, d: bell(m, d)) * 0.35)
    S["sfx_scatter_win"] = fit(sw + reverb(sw, 1.6, 3) * 0.3, 1.99)
    big = mx(choir((62, 66, 69, 74), 3.6) * 0.5, seq([62, 66, 69, 74, 78, 81, 86, 90], 0.09, 1.0, harpsichord) * 0.4)
    S["sfx_scatter_win_v2"] = fit(big + reverb(big, 2.2, 4) * 0.35, 3.67)
    # anticipation: 7.7 s of rising wind and a swelling choir (looped while a reel may land a moon)
    n = ns(7.68)
    p = np.arange(n) / n
    ant = wind(7.68, 400) * (0.3 + 0.5 * p) + choir((62, 69), 7.68, "oo") * 0.5 * p
    S["sfx_anticipation"] = fit(ant, 7.68)
    S["sfx_anticipation_start"] = fit(mx(whoosh(0.6, 200, 2500) * 0.6, toll(62, 1.0) * 0.25), 1.0)
    # symbol bursts: green-fire whoosh with a crackle, climbing per tumble
    for i in range(1, 6):
        n = ns(0.5)
        crackle = (rng.random(n) < 0.004) * rng.uniform(-1, 1, n)
        z = mx(whoosh(0.5, 400 + 150 * i, 5000) * 0.6, hp(crackle, 2000) * 0.5, glass(84 + 2 * i, 0.4) * 0.15)
        S[f"tumble_win_{i}"] = fit(z + reverb(z, 1.0, 20 + i) * 0.3, [0.996, 1.135, 1.135, 0.999, 0.99][i - 1])
    # potion (multiplier) family: glass, bubbles, cork pops
    S["sfx_multiplier_landing"] = fit(mx(glass(91, 0.5) * 0.5, bubble(600) * 0.3), 1.0)
    bub = np.zeros(ns(1.5))
    for k in range(7):
        place(bub, bubble(400 + 90 * k, 0.12) * 0.4, k * 0.09)
    S["sfx_multiplier_up"] = fit(mx(bub, seq([74, 78, 81, 86, 90], 0.07, 0.4, lambda m, d: glass(m, d)) * 0.4), 1.5)
    S["sfx_multiplier_update"] = fit(seq([86, 93, 86, 93], 0.1, 0.3, lambda m, d: glass(m, d)) * 0.45, 1.6)
    S["sfx_multiplier_reset"] = fit(whoosh(0.5, 3000, 300, rise=False) * 0.4, 0.58)
    for name, m in (("a", 81), ("b", 76)):
        c = mx(seq([m, m + 7, m + 12], 0.07, 0.6, lambda mm, d: glass(mm, d)) * 0.5, bubble(500, 0.2) * 0.3)
        S[f"sfx_multiplier_combine_{name}"] = fit(c + reverb(c, 1.0, 30) * 0.3, 1.21 if name == "a" else 1.05)
    for name, d, f0 in (("a", 0.77, 80), ("b", 2.05, 55), ("c", 1.2, 65)):
        b = mx(frame_drum(f0, d * 0.9, 1.4), whoosh(d * 0.6, 3000, 300, rise=False) * 0.4)
        S[f"sfx_multiplier_explosion_{name}"] = fit(b + reverb(b, 1.6, 40) * 0.3, d)
    S["sfx_wild_explode"] = fit(mx(war_drum(1.2) * 0.8, whoosh(1.0, 200, 3000) * 0.4), 1.4)
    mw = mx(choir((62, 66, 69, 74), 3.6) * 0.5, organ((50, 62, 66, 69), 3.6) * 0.35)
    S["sfx_multiplier_win"] = fit(mw + reverb(mw, 2.2, 41) * 0.3, 3.79)

    # win ticks: harpsichord phrases with a bell on top, longer for bigger wins
    def phrase(notes, step, d, total, seed):
        x = mx(seq(notes, step, d, harpsichord), bell(notes[-1] + 12, 1.0) * 0.25)
        return fit(x * 0.5 + reverb(x, 1.4, seed) * 0.3, total)
    S["sfx_winlevel_small"] = phrase([74, 81], 0.09, 0.5, 1.0, 50)
    S["sfx_winlevel_standard"] = phrase([74, 78, 81], 0.09, 0.5, 1.25, 51)
    S["sfx_winlevel_nice"] = phrase([74, 78, 81, 86], 0.09, 0.55, 1.47, 52)
    S["sfx_winlevel_substantial"] = phrase([74, 78, 81, 86, 81, 86, 90], 0.1, 0.6, 2.49, 53)
    end = mx(organ((62, 66, 69, 74), 1.8) * 0.5, toll(62, 1.8) * 0.3)
    S["sfx_winlevel_end"] = fit(end + reverb(end, 1.8, 54) * 0.3, 2.0)
    fan = mx(choir((62, 66, 69), 2.8) * 0.5, seq([62, 69, 74, 78, 81, 86], 0.12, 1.0, music_box) * 0.4)
    S["sfx_youwon_panel"] = fit(fan * 0.5 + reverb(fan, 2.0, 55) * 0.3, 3.0)
    # bonus start (matches the witch-fire ring and moon burst): fire swirls in, gong, choir swells, 6 s
    n = ns(6.0)
    x = np.zeros(n)
    place(x, whoosh(1.0, 200, 4000) * 0.6, 0.0)
    place(x, gong(4.5, 62) * 0.8, 0.8)
    place(x, choir((50, 57, 62, 65), 4.5, "ah") * 0.6, 1.0)
    place(x, seq([62, 65, 69, 74, 77, 81], 0.1, 1.5, music_box) * 0.3, 1.4)
    S["sfx_superfreespin"] = fit(x + reverb(x, 2.6, 60) * 0.35, 6.0)
    jg = mx(choir((62, 69, 74), 1.9, "oo") * 0.6, seq([62, 65, 69, 74, 77, 81], 0.08, 0.9, harpsichord) * 0.4)
    S["jng_intro_fs"] = fit(jg * 0.55 + reverb(jg, 1.8, 61) * 0.3, 2.0)
    rt = mx(seq([74, 77, 81, 86, 89, 93], 0.1, 0.9, music_box), toll(50, 2.0) * 0.4)
    S["sfx_fs_respins"] = fit(rt * 0.5 + reverb(rt, 2.0, 62) * 0.3, 4.06)
    # gold coin rain loop for big wins, 17 s, seamless (tail folded to the start)
    n = ns(17.125)
    x = np.zeros(n + ns(2))
    t = 0.0
    while t < 17.0:
        place(x, coin(int(rng.integers(86, 101))) * float(rng.uniform(0.08, 0.2)), t)
        t += float(rng.uniform(0.03, 0.12))
    x = x + reverb(x, 1.2, 63) * 0.4
    loop = x[:n].copy()
    loop[: ns(2)] += x[n:]
    S["sfx_bigwin_coinloop"] = loop
    return {k: norm_peak(v, 0.8) for k, v in S.items()}


# ---------------------------------------------------------------- build
def main():
    old = json.load(open(NAMES_JSON))
    names = list(old["sprite"].keys())
    loops = {k for k, v in old["sprite"].items() if len(v) > 2 and v[2]}
    print("synthesizing music ...")
    music = {"bgm_main": witchs_tower(), "bgm_freespin": witching_hour()}
    for name, key in (("big", 62), ("superwin", 64), ("mega", 65), ("epic", 67), ("max", 69)):
        music[f"bgm_winlevel_{name}"] = win_loop(key)
    print("synthesizing sfx ...")
    fx = {k: np.stack([v, v]) for k, v in sfx().items()}
    clips = {**music, **fx}
    missing = [k for k in names if k not in clips]
    extra = [k for k in clips if k not in names]
    assert not missing and not extra, f"name mismatch: missing {missing}, extra {extra}"

    gap = ns(1.0)
    parts, sprite, pos = [], {}, 0
    for k in names:
        c = clips[k]
        assert np.isfinite(c).all() and c.shape[0] == 2 and c.shape[1] > 0, k
        sprite[k] = [round(pos / SR * 1000, 3), round(c.shape[1] / SR * 1000, 3)] + ([True] if k in loops else [])
        parts += [c, np.zeros((2, gap))]
        pos += c.shape[1] + gap
    mix = np.concatenate(parts, axis=1)
    peak = np.max(np.abs(mix))
    assert peak <= 1.0, f"clipping: {peak}"
    os.makedirs(OUT, exist_ok=True)
    wav = os.path.join(OUT, "_sounds.wav")
    wavfile.write(wav, SR, (mix.T * 32767).astype(np.int16))
    for ext, args in (("ogg", ["-c:a", "libvorbis", "-q:a", "5"]), ("m4a", ["-c:a", "aac", "-b:a", "160k"]),
                      ("mp3", ["-c:a", "libmp3lame", "-b:a", "160k"])):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, *args, os.path.join(OUT, f"sounds.{ext}")],
                       check=True)
    os.remove(wav)
    out = {"sprite": sprite, "src": [f"./assets/audio/hb/sounds.{e}" for e in ("ogg", "m4a", "mp3")],
           "config": {k: {"volume": 0.8 if k.startswith("bgm") else 1} for k in names}}
    json.dump(out, open(os.path.join(OUT, "sounds.json"), "w"), indent=1)
    print(f"ok: {len(names)} sounds, {pos / SR:.1f} s, peak {peak:.2f}, files in {os.path.normpath(OUT)}")


if __name__ == "__main__":
    sys.exit(main())
