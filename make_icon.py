"""生成应用图标（液态玻璃质感），输出 .ico 供 PyInstaller 使用。

用 4 倍超采样保证抗锯齿质量，多尺寸嵌入 ICO。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # 超采样倍数
OUT = Path(__file__).resolve().parent / "ui" / "app.ico"


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def gradient_diag(size: int, c1: tuple, c2: tuple, c3: tuple) -> Image.Image:
    """左上 → 右下的三色对角渐变。"""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            if t < 0.42:
                u = t / 0.42
                r = int(lerp(c1[0], c2[0], u))
                g = int(lerp(c1[1], c2[1], u))
                b = int(lerp(c1[2], c2[2], u))
            else:
                u = (t - 0.42) / 0.58
                r = int(lerp(c2[0], c3[0], u))
                g = int(lerp(c2[1], c3[1], u))
                b = int(lerp(c2[2], c3[2], u))
            px[x, y] = (r, g, b)
    return img


def render(size: int) -> Image.Image:
    S = size * SS
    pad = int(S * 0.075)          # 留白，给阴影空间
    body = S - pad * 2
    radius = int(body * 0.272)     # 圆角比例，贴近 macOS/Windows11 图标

    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- 外阴影 ---
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [pad, pad + int(S * 0.012), pad + body, pad + body + int(S * 0.012)],
        radius=radius, fill=(24, 38, 90, 96),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, S // 34)))
    canvas = Image.alpha_composite(canvas, shadow)

    # --- 玻璃主体 ---
    grad = gradient_diag(body, (127, 178, 255), (75, 123, 255), (123, 91, 255))
    grad = grad.convert("RGBA")
    mask = rounded_mask(body, radius)
    body_img = Image.new("RGBA", (body, body), (0, 0, 0, 0))
    body_img.paste(grad, (0, 0), mask)
    canvas.paste(body_img, (pad, pad), body_img)

    # --- 顶部镜面高光（上亮下透） ---
    spec = Image.new("RGBA", (body, body), (0, 0, 0, 0))
    sp = spec.load()
    for y in range(body):
        t = y / max(1, body - 1)
        # 前 46% 迅速衰减，之后完全透明
        a = int(200 * max(0.0, 1 - t / 0.46) ** 1.6)
        if a:
            for x in range(body):
                sp[x, y] = (255, 255, 255, a)
    spec.putalpha(Image.composite(spec.split()[3], Image.new("L", (body, body), 0), mask))
    canvas.paste(spec, (pad, pad), spec)

    # --- 边缘亮线：模拟玻璃厚度 ---
    rim = Image.new("RGBA", (body, body), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle(
        [1, 1, body - 2, body - 2], radius=radius, outline=(255, 255, 255, 170),
        width=max(2, int(S * 0.008)),
    )
    canvas.paste(rim, (pad, pad), rim)

    # --- 勾选符号 ---
    d = ImageDraw.Draw(canvas)
    lw = int(S * 0.088)
    p1 = (pad + body * 0.245, pad + body * 0.505)
    p2 = (pad + body * 0.425, pad + body * 0.672)
    p3 = (pad + body * 0.762, pad + body * 0.345)
    d.line([p1, p2], fill=(255, 255, 255, 255), width=lw, joint="curve")
    d.line([p2, p3], fill=(255, 255, 255, 255), width=lw, joint="curve")
    # 圆头
    rr = lw // 2
    for pt in (p1, p2, p3):
        d.ellipse([pt[0] - rr, pt[1] - rr, pt[0] + rr, pt[1] + rr], fill=(255, 255, 255, 255))

    # --- 下方清单细线 ---
    ly = pad + body * 0.795
    d.line(
        [(pad + body * 0.245, ly), (pad + body * 0.645, ly)],
        fill=(255, 255, 255, 168), width=int(S * 0.055),
    )

    return canvas.resize((size, size), Image.LANCZOS)


def main() -> int:
    sizes = [256, 128, 64, 48, 32, 16]
    imgs = [render(s) for s in sizes]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 用最大尺寸作为基准保存多尺寸 ICO
    imgs[0].save(OUT, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[1:])
    print(f"图标已生成: {OUT}")
    print(f"尺寸: {sizes}")
    print(f"大小: {OUT.stat().st_size / 1024:.1f} KB")
    # 同时导出一张 PNG 便于预览
    preview = OUT.parent / "icon_preview.png"
    imgs[0].save(preview)
    print(f"预览图: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
