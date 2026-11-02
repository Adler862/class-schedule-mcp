"""生成更精致的课程档案板 v2。

Blender 坐标：x=厚度，y=长度，z=高度；导出 glTF 时转为 Y-up。
只保留 archive_body / archive_face 两个网格，不覆盖旧版 GLB。

用法：
  blender.exe -b -P art/build_archive_v2.py
"""
import bpy
import os

W, H, T = 0.17, 1.30, 1.486
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'archive-board-v2.glb')

bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def cube(name, dimensions, location):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def subtract(body, cutter):
    activate(body)
    mod = body.modifiers.new('paper_layer_cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# 主体采用更大的多段倒角；切槽只落在顶边和尾边，避开 -y 编号脊面。
body = cube('archive_body', (W, T, H), (0, 0, 0))
body.data.name = 'archive_body'
activate(body)
bevel = body.modifiers.new('soft_board_edges', 'BEVEL')
bevel.width = 0.018
bevel.segments = 5
bevel.limit_method = 'ANGLE'
bevel.angle_limit = 0.6
bevel.harden_normals = True
bpy.ops.object.modifier_apply(modifier=bevel.name)

# 三组 2 mm 宽、1 mm 浅的纸层压痕，在相邻两边形成对应关系。
for x in (-0.046, 0.0, 0.046):
    top_cut = cube(
        'temporary_top_cut',
        (0.002, T - 0.05, 0.003),
        (x, 0, H / 2 + 0.0005),
    )
    subtract(body, top_cut)

    tail_cut = cube(
        'temporary_tail_cut',
        (0.002, 0.003, H - 0.05),
        (x, T / 2 + 0.0005, 0),
    )
    subtract(body, tail_cut)

activate(body)
for polygon in body.data.polygons:
    polygon.use_smooth = True
weighted = body.modifiers.new('weighted_board_normals', 'WEIGHTED_NORMAL')
weighted.keep_sharp = True
weighted.weight = 50
bpy.ops.object.modifier_apply(modifier=weighted.name)

body.data.materials.clear()
body.data.materials.append(bpy.data.materials.new('body_side'))
body.data.materials.append(bpy.data.materials.new('body_spine'))
for polygon in body.data.polygons:
    polygon.material_index = 1 if polygon.normal.y < -0.85 else 0


# 纸面为封闭薄网格。正反面同步轻微翘曲，保持 3.2 mm 的实际厚度。
# 正面 UV 按网格显式写入，不依赖 cube_project / pack_islands。
PAPER_W = T - 0.056
PAPER_H = H - 0.056
PAPER_FRONT_X = -0.0886
PAPER_BACK_X = -0.0854
NY, NZ = 28, 24

samples = []
for j in range(NZ + 1):
    v = j / NZ
    z = (v - 0.5) * PAPER_H
    for i in range(NY + 1):
        u = i / NY
        y = (u - 0.5) * PAPER_W
        edge_y = abs(2 * u - 1)
        edge_z = abs(2 * v - 1)
        curl = (
            0.00065 * (edge_y ** 12 + edge_z ** 12)
            + 0.00070 * (edge_y * edge_z) ** 8
        )
        samples.append((y, z, u, v, curl))

count = len(samples)
vertices = []
for x in (PAPER_FRONT_X, PAPER_BACK_X):
    vertices.extend((x - curl, y, z) for y, z, _u, _v, curl in samples)

faces = []
front_face_count = 0
for j in range(NZ):
    for i in range(NY):
        f00 = j * (NY + 1) + i
        f10 = f00 + 1
        f01 = f00 + NY + 1
        f11 = f01 + 1
        b00, b10, b01, b11 = f00 + count, f10 + count, f01 + count, f11 + count
        faces.append((f00, f01, f11, f10))  # 法线朝 -x
        faces.append((b00, b10, b11, b01))  # 法线朝 +x
        front_face_count += 1

# 沿正面外边界连接背纸，构成单一封闭网格。
perimeter = []
perimeter.extend(j * (NY + 1) for j in range(NZ + 1))
perimeter.extend(NZ * (NY + 1) + i for i in range(1, NY + 1))
perimeter.extend(j * (NY + 1) + NY for j in range(NZ - 1, -1, -1))
perimeter.extend(i for i in range(NY - 1, 0, -1))
for index, front_a in enumerate(perimeter):
    front_b = perimeter[(index + 1) % len(perimeter)]
    faces.append((front_a, front_a + count, front_b + count, front_b))

mesh = bpy.data.meshes.new('archive_face')
mesh.from_pydata(vertices, [], faces)
mesh.update()
face = bpy.data.objects.new('archive_face', mesh)
bpy.context.collection.objects.link(face)

uv_layer = mesh.uv_layers.new(name='UVMap')
for loop in mesh.loops:
    _y, _z, u, v, _curl = samples[loop.vertex_index % count]
    uv_layer.data[loop.index].uv = (u, v)
for index, polygon in enumerate(mesh.polygons):
    polygon.use_smooth = index < front_face_count * 2

mesh.materials.append(bpy.data.materials.new('face_paper'))

# 导出前确认主体原始边界未被细节改动。
activate(body)
assert all(abs(a - b) < 1e-6 for a, b in zip(body.dimensions, (W, T, H)))
assert len([obj for obj in bpy.data.objects if obj.type == 'MESH']) == 2

bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLB',
    use_selection=False,
    export_apply=True,
    export_yup=True,
)
print('WROTE', OUT, 'objects=2', 'body_faces=%d' % len(body.data.polygons),
      'paper_faces=%d' % len(face.data.polygons))
