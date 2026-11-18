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


def adapt_generated_sources(output):
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
