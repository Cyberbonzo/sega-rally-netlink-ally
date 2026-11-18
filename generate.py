"""Generate the native modules from a user-supplied US NetLink disc."""
import hashlib
import json
from pathlib import Path
import re
import sys


MODULES = {
    "RALLY": ("RALLY/0RALLY.DAT", 0x06009000,
              "ccaf9882ae555c31f608d2ee0a03a1c15d7964c4257ae91cfc230e04e89f7278"),
    "H2H": ("GAMEINFO/H2HLIBUS.BIN", 0x06002F00,
            "7d988e45bb18b58e0dcbe713eb1c7b3694de2eca80ecaf77357c797c12971eb6"),
}


def replace_one(text, original, replacement):
    if text.count(original) != 1:
        raise ValueError(f"Unexpected generator output near {original[:60]!r}")
    return text.replace(original, replacement)


def adapt_decoder(text):
    # Between CD reads the stream decoder saves its guest registers and exits
    # to its caller. Later it re-enters immediately after the suspended read.
    entry = "void f_0601E55C(SH2Context& c) {"
    start = text.index(entry)
    end = text.index("\n}", start)
    body = text[start:end]
    continuations = re.findall(r"f_0601E690\(c\); if \(c.pc != 0x([\dA-F]{8})u\) return;", body)
    if len(set(continuations)) != 7:
        raise ValueError("The expected decoder continuations are missing")
    switch = ["case 0: break;"]
    for pc in continuations:
        instruction = next(line for line in body.splitlines() if f"// {pc} " in line)
        body = replace_one(body, instruction, f"resume_{pc}:\n{instruction}")
        switch.append(f"case 0x{pc}u: goto resume_{pc};")
    switch.append("default: sh2_bad_return(c, entry); return;")
    wrapper = (
        "static void resume_decoder(SH2Context&, uint32_t);\n"
        + entry + " resume_decoder(c, 0); }\n"
        + "static void resume_decoder(SH2Context& c, uint32_t entry) {\n"
        + "switch (entry) {\n" + "\n".join(switch) + "\n}"
    )
    text = text[:start] + replace_one(body, entry, wrapper) + text[end:]
    exit_line = next(line for line in text.splitlines() if "// 0601E726 " in line)
    updated = replace_one(exit_line, "c.pc = x; return;", "c.pc = x; resume_decoder(c, x); return;")
    return replace_one(text, exit_line, updated)


def select_metric_units(output):
    # Boot keeps the US language/region. These five HUD decisions select the
    # stock metric art, tile layout and speed multiplier.
    decisions = {"06009474", "06016D2E", "06016D60", "06016DC6", "0601764A"}
    found = set()
    for path in output.glob("p_rally_*.cpp"):
        source = original = path.read_text(encoding="utf-8")
        for pc in decisions:
            metric = f"c.t = true;  // {pc} "
            region = f"c.t = (c.r[0] & 0x1u) == 0;  // {pc} "
            if region in source or metric in source:
                source = source.replace(region, metric)
                found.add(pc)
        if source != original:
            path.write_text(source, encoding="utf-8")
    if found != decisions:
        raise ValueError(f"Missing speedometer branches: {sorted(decisions - found)}")


def widen_projection_clip(output):
    # The master and slave render contexts share this bind routine. The packed
    # 176x112 half-extents feed both vertex rejection and quad clipping.
    needle = "    { const uint32_t x = c.pr; c.gbr = c.r[14]; c.pc = x; return; }  // 0601F7D8 "
    local = """    static const bool wide_race_enabled = std::getenv("SR_NETLINK_WIDE") != nullptr;
    if (wide_race_enabled) {
        const uint32_t bounds_address = c.r[14] + 24;
        const uint32_t bounds = ld32(bounds_address);
        if (bounds == 0x00B00070u || bounds == 0x00EB0070u) {
            const uint32_t wanted = ::rally_course_scene() ? 0x00EB0070u : 0x00B00070u;
            if (bounds != wanted) st32(bounds_address, wanted);
        }
    }
"""
    found = 0
    for path in output.glob("p_rally_*.cpp"):
        source = path.read_text(encoding="utf-8")
        if needle not in source:
            continue
        found += source.count(needle)
        if local in source:
            continue
        end = source.index(needle)
        label = "L_0601F7D8:\n"
        start = source.rindex(label, 0, end) + len(label)
        existing = source[start:end].strip()
        if existing and not existing.startswith("static const bool wide_race_enabled ="):
            raise ValueError("Unexpected code at the graphics context bind")
        source = source[:start] + local + source[end:]
        if "#include <cstdlib>" not in source:
            source = "#include <cstdlib>\n" + source
        if "extern bool rally_course_scene();" not in source:
            source = "extern bool rally_course_scene();\n" + source
        path.write_text(source, encoding="utf-8")
    if found != 1:
        raise ValueError("Expected one graphics context bind in the US NetLink program")


def extend_stage_clock(output):
    # Championship (first stage and carry-over) and Practice call the allowance
    # routine at stage setup. Checkpoints call it separately. The timer stores
    # binary seconds above a byte holding the sub-second tick.
    starts = {"06019E5E", "06019E82", "06019EB0"}
    bonus = "    st32(c.r[13] + 52, ld32(c.r[13] + 52) + (10u << 8));"
    seen = set()
    for path in output.glob("p_rally_*.cpp"):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        patched = []
        for line in lines:
            match = re.search(r"// ([0-9A-F]{8}) bra 0x0601A8A8 ; mov #0,r3", line)
            if match and match[1] in starts:
                seen.add(match[1])
                if not patched or patched[-1].strip() != bonus.strip():
                    patched.append(bonus + "\n")
            patched.append(line)
        updated = "".join(patched)
        if updated != source:
            path.write_text(updated, encoding="utf-8")
    if seen != starts:
        raise ValueError("Missing timed-stage initializer in the US NetLink program")


def resume_time_attack_result(output):
    # The second Time Attack finish state leaves its return address on the guest
    # stack. On SH-2 this runs the HUD epilogue twice before reaching its caller.
    # Resume it in that caller, retaining both passes and their original effects.
    guard = "if (c.pc != 0x060167FAu) return; }  // 060167F6 "
    paths = [p for p in output.glob("p_rally_*.cpp") if guard in p.read_text(encoding="utf-8")]
    if len(paths) != 1:
        raise ValueError("Missing Time Attack result dispatcher")
    p = paths[0]
    text = p.read_text(encoding="utf-8")
    p.write_text(replace_one(text, guard, "if (c.pc == 0x06017B3Eu) f_06017B3E(c); " + guard),
                 encoding="utf-8")


def watch_native_save_load(output):
    entry = "void f_060391B6(SH2Context& c) {"
    finish = "    { const uint32_t x = c.pr; c.pc = x; return; }  // 060391F2 rts ; nop"
    candidates = [path for path in output.glob("p_rally_*.cpp") if entry in path.read_text(encoding="utf-8")]
    if len(candidates) != 1:
        raise ValueError("Missing unique cabinet progress loader")
    path = candidates[0]
    text = path.read_text(encoding="utf-8")
    if "::rally_progress_load_begin();" not in text:
        text = replace_one(text, entry, entry + "\n    ::rally_progress_load_begin();")
        text = replace_one(text, finish, "    ::rally_progress_load_end();\n" + finish)
        declarations = "void rally_progress_load_begin();\nvoid rally_progress_load_end();\n"
        path.write_text(declarations + text, encoding="utf-8")
    # Commit edits as the garage slider writes its working value. Menu item 6
    # is the explicit SAVE slot picker and must retain the original behaviour.
    store = "    st8(c.r[1], c.r[3]);  // 060308F2 mov.b r3,@r1"
    edits = [path for path in output.glob("p_rally_*.cpp") if store in path.read_text(encoding="utf-8")]
    if len(edits) != 1:
        raise ValueError("Missing unique car setup edit")
    path = edits[0]
    text = path.read_text(encoding="utf-8")
    if "::rally_garage_edited();" in text:
        return
    edit = """    const bool garage_changed = c.r[1] >= 0x060A88F3u && c.r[1] <= 0x060A88F8u
                             && ld8(c.r[1]) != uint8_t(c.r[3]);
""" + store + "\n    if (garage_changed) ::rally_garage_edited();"
    path.write_text("void rally_garage_edited();\n" + replace_one(text, store, edit), encoding="utf-8")


def adapt_generated_sources(output):
    resume_time_attack_result(output)
    watch_native_save_load(output)
    widen_projection_clip(output)
    extend_stage_clock(output)
    select_metric_units(output)
    decoded = False
    omitted = set()
    for path in sorted(output.glob("p_rally_*.cpp")):
        text = original = path.read_text(encoding="utf-8")
        if "void f_0601E55C(SH2Context& c) {" in text:
            text = adapt_decoder(text)
            decoded = True
        # Both loaders tail-call the same routine with their caller's return
        # address still in PR. The extra push would leak one guest stack slot.
        for pc in ("06009920", "06009974"):
            matches = [line for line in text.splitlines() if f"// {pc} " in line]
            if matches:
                if len(matches) != 1 or pc in omitted:
                    raise ValueError(f"Ambiguous loader entry at {pc}")
                text = replace_one(text, matches[0] + "\n", "")
                omitted.add(pc)
        if text != original:
            path.write_text(text, encoding="utf-8")
    if not decoded or len(omitted) != 2:
        raise ValueError("Expected offline loader or decoder not found")

    # The relocated loop rewrites two immediate operands between game states.
    path = output / "p_loop_000.cpp"
    text = path.read_text(encoding="utf-8")
    for reg, addr in ((0, 0x060CA001), (4, 0x060CA013)):
        text = replace_one(text, f"c.r[{reg}] = 0x2u;", f"c.r[{reg}] = (uint32_t)(int8_t)ld8(0x{addr:08X}u);")
    path.write_text(text, encoding="utf-8")


def generate_game(upstream, cue, work):
    sys.path.insert(0, str(upstream / "src"))
    from saturnrecomp.disc import Disc
    from saturnrecomp.recomp.__main__ import generate

    disc = Disc(str(cue))
    if (len(disc.tracks) != 17 or disc.tracks[0].is_audio
            or not all(track.is_audio for track in disc.tracks[1:])):
        raise ValueError("Expected a NetLink disc with one data track and sixteen audio tracks")
    if len({track.path for track in disc.tracks}) != 17:
        raise ValueError("Supply a split-track CUE with one BIN per track, or use the original CHD")
    if disc.iso.find("RALLY").lba != 32:
        raise ValueError("Unsupported NetLink ISO directory layout")
    seeds = json.loads(Path(__file__).with_name("seeds.json").read_text())
    inputs = work / "inputs"
    inputs.mkdir(exist_ok=True)
    specs = []
    for name, (member, address, digest) in MODULES.items():
        binary = disc.read_file(disc.iso.find(member))
        if hashlib.sha256(binary).hexdigest() != digest:
            raise ValueError(f"Unsupported disc revision. Checksum mismatch for {member}")
        path = inputs / name
        path.write_bytes(binary)
        specs.append((name, str(path), address, [int(pc, 16) for pc in seeds[name]]))
    loop = inputs / "loop"
    loop.write_bytes((inputs / "RALLY").read_bytes()[0x1D0:0x1F8])
    specs.append(("LOOP", str(loop), 0x060CA000, []))
    out = work / "generated"
    out.mkdir(exist_ok=True)
    generate(specs, str(out), callable_entries={"LOOP"}, runtime_literals={"LOOP"},
             unwind_returns={"RALLY"})
    adapt_generated_sources(out)
    return out
