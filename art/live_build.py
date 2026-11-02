"""在已经打开的 Blender 窗口里把档案板建出来——你能实时看到它成型。

通过 MCP 的 execute_code 发进 GUI 版的 Blender，跑完模型就留在场景里，
可以自己旋转查看。
"""
import bpy

W, H, T = 0.17, 1.30, 1.486


def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


def box(name, sx, sy, sz, loc, bevel=0.006, seg=2, rgb=(0.90, 0.88, 0.85)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.data.name = name
    o.scale = (sx / 2, sy / 2, sz / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1.0)
    bpy.ops.object.mode_set(mode='OBJECT')
    if bevel:
        md = o.modifiers.new('bev', 'BEVEL')
        md.width = bevel
        md.segments = seg
        md.limit_method = 'ANGLE'
        md.angle_limit = 0.6
        bpy.ops.object.modifier_apply(modifier=md.name)
    mat = bpy.data.materials.new(name + '_mat')
    mat.diffuse_color = (*rgb, 1.0)
    o.data.materials.append(mat)
    return o


wipe()

# 本体：外侧一色，脊面（-y）另一色，导出后脊面正好是 three 里的 +z
body = box('archive_body', W, T, H, (0, 0, 0), bevel=0.008, seg=2, rgb=(0.84, 0.82, 0.78))
body.data.materials.append(bpy.data.materials.new('body_spine'))
for p in body.data.polygons:
    if p.normal.y < -0.85:
        p.material_index = 1

# 正面那层纸，比本体薄、略凸
box('archive_face', 0.012, T - 0.04, H - 0.04, (-W / 2 - 0.004, 0, 0),
    bevel=0.003, seg=1, rgb=(0.98, 0.97, 0.95))

# 灯光
light_data = bpy.data.lights.new('key', type='AREA')
light_data.energy = 60
light_data.size = 3
light = bpy.data.objects.new('key', light_data)
light.location = (-1.6, -1.2, 1.8)
bpy.context.collection.objects.link(light)

# 相机：正对 -x 那面
cam_data = bpy.data.cameras.new('cam')
cam_data.lens = 85
cam = bpy.data.objects.new('cam', cam_data)
cam.location = (-1.35, 0, 0)
cam.rotation_euler = (1.5708, 0, -1.5708)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

# 视口切到相机视角，省得还要自己找
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for region in area.regions:
            if region.type == 'WINDOW':
                with bpy.context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_camera()
        area.spaces[0].shading.type = 'MATERIAL'
        break

print('LIVE_BUILD_DONE objects=%d' % len(bpy.data.objects))
