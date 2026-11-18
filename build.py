#!/usr/bin/env python3
"""Build an offline Linux port from the original NetLink disc."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

sys.dont_write_bytecode = True
from generate import generate_game


ROOT = Path(__file__).resolve().parent
UPSTREAM = "https://github.com/callumjenkins/saturn-recomp.git"
REVISION = "032fd3bc8a6c3e5d23853f53b951aa1446a9dfc1"


def run(*args, **options):
    subprocess.run(args, check=True, **options)


def fetch_runtime(work, origin):
    checkout = work / "upstream"
    patch = ROOT / "runtime.patch"
    if checkout.exists():
        # Keep the prior build and its local edits available when updating.
        check = subprocess.run(["git", "-C", checkout, "apply", "--reverse", "--check", patch],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            revision = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
            if revision != REVISION:
                raise ValueError("Unexpected runtime revision in the build directory")
            origin = str(checkout)
            checkout = work / ("upstream-" + hashlib.sha256(patch.read_bytes()).hexdigest()[:16])
    if not checkout.exists():
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            clean = Path(tmp) / "upstream"
            run("git", "init", "--quiet", clean)
            run("git", "-C", clean, "fetch", "--quiet", "--depth=1", origin, REVISION)
            run("git", "-C", clean, "checkout", "--quiet", "--detach", "FETCH_HEAD")
            run("git", "-C", clean, "apply", "--index", ROOT / "runtime.patch")
            clean.rename(checkout)
    revision = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("Unexpected runtime revision in the build directory")
    run("git", "-C", checkout, "apply", "--reverse", "--check", ROOT / "runtime.patch")
    return checkout


def as_cue(image, work):
    if image.suffix.lower() == ".cue":
        return image
    if image.suffix.lower() != ".chd":
        raise ValueError("Supply a CUE or a CHD")
    # Bind the cached extraction to this input, even when the file is replaced.
    with image.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    target = work / ("disc-" + digest)
    if not target.exists():
        tool = shutil.which("chdman")
        if not tool:
            raise ValueError("CHD input needs chdman. You can also supply a split-track CUE directly")
        with tempfile.TemporaryDirectory(dir=work) as tmp:
            extracted = Path(tmp) / "media"
            extracted.mkdir()
            run(tool, "extractcd", "--splitbin", "-i", image, "-o", "disc.cue", cwd=extracted)
            extracted.rename(target)
    return target / "disc.cue"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc", type=Path)
    parser.add_argument("--work", type=Path, default=ROOT / "local")
    parser.add_argument("--upstream", default=UPSTREAM, help="URL or local git repository holding the pinned revision")
    parser.add_argument("--headless", action="store_true", help="build the command-line test host without SDL")
    parser.add_argument("--smoke-test", action="store_true", help="run a scripted Desert race after building")
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    disc = args.disc.resolve(strict=True)
    cue = as_cue(disc, work)
    upstream = fetch_runtime(work, args.upstream)
    source = generate_game(upstream, cue, work)
    build = work / ("build-headless" if args.headless else "build")
    run("cmake", "-S", source, "-B", build, "-DCMAKE_BUILD_TYPE=Release",
        f"-DSATURN_RUNTIME={upstream / 'runtime'}",
        f"-DSATURN_NO_SDL={'ON' if args.headless else 'OFF'}",
        f"-DSATURN_REQUIRE_SDL={'OFF' if args.headless else 'ON'}")
    run("cmake", "--build", build, "--target", "saturn", "--config", "Release",
        "--parallel", os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL", "4"))
    suffix = ".exe" if os.name == "nt" else ""
    binary = build / ("saturn" + suffix)
    if not binary.exists():
        binary = build / "Release" / ("saturn" + suffix)
    if args.smoke_test:
        output = work / "smoke"
        output.mkdir(exist_ok=True)
        inputs = ("360:START,372:,600:START,612:,1250:A,1262:,1460:A,1472:,1670:A,1682:,"
                  "1850:A,1862:,2050:START,2062:,2400:A,2412:,2600:X,2612:B,3300:B+RIGHT,3320:B")
        env = dict(os.environ, SR_NETLINK_RACE_BOOT="1", SR_NETLINK_WIDE="1")
        cmd = [binary, "--headless", "--interp", "--cue", cue, "--out", output, "--save", "-",
               "--vblanks", "4000", "--shot", "2800,4000", "--input", inputs]
        with (output / "run.log").open("w") as log:
            run(*cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
        if "after 4000 VBlanks" not in (output / "run.log").read_text():
            raise RuntimeError(f"The race ended early. See {output / 'run.log'}")
        print(f"Race test completed. Captures and log in {output}")
    if not args.headless:
        install = work / "game"
        install.mkdir(exist_ok=True)
        shutil.copy2(binary, install / ("sega-rally-netlink" + suffix))
        for name in ("controls.ini", "play.sh"):
            if name == "play.sh" or not (install / name).exists():
                shutil.copy2(ROOT / name, install / name)
        (install / "play.sh").chmod(0o755)
        (install / "cue.path").write_text(str(cue) + "\n", encoding="utf-8")
        print(f"Linux launcher: {install / 'play.sh'}")


if __name__ == "__main__":
    main()
