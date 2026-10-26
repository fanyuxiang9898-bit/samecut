"""Original generated geometric test art; no downloaded or personal media."""
import random
from pathlib import Path
from PIL import Image, ImageDraw
from .core import SamecutError, command, run


def demo(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise SamecutError("Demo directory must be new or empty.")
    assets = root/"photos"
    assets.mkdir(parents=True,exist_ok=True)
    palette = [(21,43,62),(214,86,57),(103,130,91),(100,76,141)]
    for i,color in enumerate(palette):
        im = Image.new("RGB",(640,360),color)
        draw = ImageDraw.Draw(im)
        rng = random.Random(i)
        for j in range(8):
            x,y = rng.randrange(0,540),rng.randrange(0,260)
            draw.ellipse((x,y,x+70,y+70),fill=tuple(min(255,c+60+j*3) for c in color))
        im.save(assets/f"{i:02d}.png")
    reference = root/"reference.mp4"
    command(["ffmpeg","-v","error","-y","-framerate","1","-i",assets/"%02d.png",
             "-f","lavfi","-i","sine=frequency=330:duration=4","-t","4","-r","30",
             "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",reference])
    return run(str(reference),assets,root/"output",aliases=["samecut","YOUR STORY"],
               reviewed_clean=True,width=640,threshold=.12)
