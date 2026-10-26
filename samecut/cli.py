import argparse
import sys
from pathlib import Path

from .core import SamecutError, run


def main():
    parser = argparse.ArgumentParser(description="Samecut · reference + photos → local MP4")
    sub = parser.add_subparsers(dest="command",required=True)
    edit = sub.add_parser("run",help="Analyze reference and render a unique-photo edit")
    edit.add_argument("--reference",required=True,help="Local MP4 or complete Douyin share text")
    edit.add_argument("--assets",required=True,help="Folder of photos")
    edit.add_argument("--output",required=True,help="New output directory")
    edit.add_argument("--aliases",nargs="+",default=["chance","QIANCHENG"])
    edit.add_argument("--manifest",help="JSON object keyed by photo filename")
    edit.add_argument("--reviewed-clean",action="store_true",help="You have visually checked all unmarked photos for watermarks")
    edit.add_argument("--recent-days",type=int,help="Require a dated photo in this many calendar days, including today")
    edit.add_argument("--as-of",help="YYYY-MM-DD; defaults to local calendar date")
    edit.add_argument("--width",type=int,default=1280)
    edit.add_argument("--threshold",type=float,default=.23,help="FFmpeg scene score threshold")
    edit.add_argument("--font",help="Local font for custom text, including Chinese")
    web = sub.add_parser("serve",help="Open a local-only upload interface")
    web.add_argument("--port",type=int,default=8765)
    web.add_argument("--workdir",default="runs")
    demo = sub.add_parser("demo",help="Create original synthetic assets and run a smoke demo")
    demo.add_argument("--output",default="runs/demo")
    args = vars(parser.parse_args())
    action = args.pop("command")
    try:
        if action == "run":
            print(run(**args))
        elif action == "serve":
            from .web import serve
            serve(**args)
        else:
            from .demo import demo
            print(demo(Path(args["output"])))
    except (SamecutError, OSError, ValueError) as exc:
        print(f"Samecut: {exc}",file=sys.stderr)
        raise SystemExit(2)
