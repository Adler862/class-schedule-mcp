"""生成"课表档案板"的 GLB：一块带倒角的薄板 + 表面一层略凸的纸面。

在 three 里板子的尺寸是 x=0.17(厚) y=1.30(高) z=1.486(长)。
Blender 是 Z-up，导出 glTF 时 +Z→+Y、+Y→-Z，
所以这里建成 (x=0.17, y=-1.486, z=1.30)，落地后正好对上。

用法：
  blender.exe -b -P art/build_archive.py
"""
import bpy
import os

W, H, T = 0.17, 1.30, 1.486     # three 里的 厚 / 高 / 长

bpy.ops.wm.read_factory_settings(use_empty=True)


def box(name, sx, sy, sz, loc, bevel=0.006, seg=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.data.name = name      # 导出的 mesh 名要跟着走，否则解析时拿不到
    o.scale = (sx, sy, sz)      # size=1 的 cube 已经是 1 单位边长，不是半径
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # 先给 UV：一块板只要把六个面各自铺满 0–1 就够了，
    # 正面拿到的就是"整张课表贴满这一面"
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1.0)
    # cube_project 给的 UV 范围不是 0-1（按立方体尺寸走），
    # pack 一下让每个面各自铺满 0-1，贴图才能正好盖住一整面
    bpy.ops.uv.pack_islands(rotate=False, margin=0.0)
    bpy.ops.object.mode_set(mode='OBJECT')

    if bevel:
        m = o.modifiers.new('bev', 'BEVEL')
        m.width = bevel
        m.segments = seg
        m.limit_method = 'ANGLE'
        m.angle_limit = 0.6
        bpy.ops.object.modifier_apply(modifier=m.name)
    return o


# 主体：厚度 W、长 T、高 H（Blender 里 y 放"长"，z 放"高"）
body = box('archive_body', W, T, H, (0, 0, 0), bevel=0.008, seg=2)

# 主体要分两个材质槽：侧面一色，脊面（-y，导出后是 glTF 的 +z）另一色。
# 不分槽的话整个 body 是单 primitive，接进 three 就没法给脊面单独贴编号，
# 档案架上那排 NO.xx 会直接消失。
body.data.materials.append(bpy.data.materials.new('body_side'))
body.data.materials.append(bpy.data.materials.new('body_spine'))
for poly in body.data.polygons:
    if poly.normal.y < -0.85:
        poly.material_index = 1

# 正面那层纸：比主体薄一点，朝 -x 微微凸出
face = box('archive_face', 0.012, T - 0.04, H - 0.04,
           (-W / 2 - 0.004, 0, 0), bevel=0.003, seg=1)

# 顶部标签夹先不做：它在正视图里就是板外浮着的一小块白，
# 起了反作用。等以后有斜视角展示时再加回来。

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'archive-board.glb')
bpy.ops.export_scene.gltf(
    filepath=out, export_format='GLB',
    use_selection=False, export_apply=True,
    export_yup=True,
)
tris = sum(len(o.data.loop_triangles) for o in bpy.data.objects if o.type == 'MESH')
print('WROTE', out, 'objects=%d' % len(bpy.data.objects))
