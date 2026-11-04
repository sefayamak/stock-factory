"""Genuine vector production -- scope-limited and honest about it.

Status: VERIFIED_WORKING for procedural geometric icons/patterns only.
There is no AI model wired up that outputs real vector paths for open-ended
creative vector illustrations (that would need a dedicated vector-capable
model or a raster->vector autotrace step, neither of which is configured).

This module builds real SVG documents from actual `<path>`/`<circle>`/
`<rect>` geometry -- never a raster image embedded in an SVG/EPS wrapper,
which the directive explicitly forbids. It currently only covers simple
procedural icon/pattern templates (geometric shapes, repeating motifs).
Creative/illustrative vector production stays BLOCKED until a real
vector-capable generation path (model or autotrace pipeline) is added.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

BLOCKED_CREATIVE_VECTOR_REASON = (
    "No vector-capable image model or raster-to-vector autotrace pipeline is "
    "configured. Only procedural geometric templates (see generate_polygon_icon, "
    "generate_repeating_pattern) produce real vector paths today; open-ended "
    "creative vector illustration is BLOCKED, not simulated."
)


@dataclass
class VectorAsset:
    svg: str
    kind: str  # 'icon' | 'pattern'
    is_genuine_vector: bool = True  # always True here: we never embed raster


def generate_polygon_icon(sides: int, size: int = 512, fill: str = '#2b2b2b') -> VectorAsset:
    if sides < 3:
        raise ValueError('a polygon needs at least 3 sides')
    cx = cy = size / 2
    r = size * 0.4
    points = []
    for i in range(sides):
        angle = (2 * math.pi * i / sides) - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append(f'{x:.2f},{y:.2f}')
    path_points = ' '.join(points)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">'
        f'<polygon points="{path_points}" fill="{fill}" /></svg>'
    )
    return VectorAsset(svg=svg, kind='icon')


def generate_repeating_pattern(tile: int = 64, grid: int = 8, fill: str = '#3a6ea5') -> VectorAsset:
    size = tile * grid
    shapes = []
    for row in range(grid):
        for col in range(grid):
            x, y = col * tile, row * tile
            r = tile * 0.35
            shapes.append(f'<circle cx="{x + tile/2}" cy="{y + tile/2}" r="{r}" fill="{fill}" />')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">' + ''.join(shapes) + '</svg>'
    return VectorAsset(svg=svg, kind='pattern')


def validate_genuine_vector(svg_text: str) -> tuple[bool, str]:
    """Rejects anything that is an SVG wrapper around a raster image
    (the directive's explicit anti-pattern) rather than real path/shape data."""
    lowered = svg_text.lower()
    if '<image' in lowered or 'data:image' in lowered:
        return False, 'raster_embedded_in_svg_container'
    if not any(tag in lowered for tag in ('<path', '<polygon', '<circle', '<rect', '<ellipse', '<line')):
        return False, 'no_vector_geometry_found'
    return True, 'pass'
