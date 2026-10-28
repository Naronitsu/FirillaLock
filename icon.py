"""Draws the app icon: an eggplant with a padlock."""
from PIL import Image, ImageDraw, ImageFilter

S = 1024  # draw large, downscale for smooth edges


def _eggplant():
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # body: big belly + narrower neck, drawn upright then rotated
    d.ellipse((250, 380, 774, 960), fill="#5b2a86")
    d.ellipse((345, 150, 679, 600), fill="#5b2a86")
    d.polygon([(345, 380), (679, 380), (774, 650), (250, 650)], fill="#5b2a86")
    # shading and highlight
    shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse((470, 420, 900, 1000), fill=(30, 8, 60, 90))
    shade = shade.filter(ImageFilter.GaussianBlur(40))
    mask = layer.split()[3]
    shade.putalpha(Image.eval(Image.composite(shade.split()[3], Image.new("L", (S, S), 0), mask), lambda v: v))
    layer = Image.alpha_composite(layer, shade)
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((320, 470, 420, 780), fill=(210, 160, 255, 120))
    layer = Image.alpha_composite(layer, hl.filter(ImageFilter.GaussianBlur(14)))
    # calyx + stem
    d = ImageDraw.Draw(layer)
    d.polygon([(512, 175), (400, 130), (360, 230), (300, 190), (350, 300),
               (440, 270), (512, 330), (584, 270), (674, 300), (724, 190),
               (664, 230), (624, 130)], fill="#3f9a45")
    d.polygon([(480, 150), (544, 150), (570, 30), (500, 30)], fill="#2f7d37")
    return layer.rotate(28, resample=Image.BICUBIC, center=(512, 560))


def _padlock():
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = 560, 600, 960, 960
    d.arc((620, 430, 900, 740), 180, 360, fill="#2b2b33", width=70)   # shackle outline
    d.arc((636, 446, 884, 724), 180, 360, fill="#c9ccd6", width=38)   # shackle
    d.rounded_rectangle((x0 - 14, y0 - 14, x1 + 14, y1 + 14), 70, fill="#2b2b33")
    d.rounded_rectangle((x0, y0, x1, y1), 58, fill="#f2b632")
    d.rounded_rectangle((x0 + 20, y0 + 20, x1 - 20, y0 + 120), 40, fill="#f8d067")
    d.ellipse((710, 715, 810, 815), fill="#2b2b33")                    # keyhole
    d.polygon([(738, 790), (782, 790), (800, 890), (720, 890)], fill="#2b2b33")
    return layer


def make_icon(size=256):
    img = Image.alpha_composite(_eggplant(), _padlock())
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    from pathlib import Path
    here = Path(__file__).parent
    big = make_icon(256)
    big.save(here / "icon.png")
    big.save(here / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
