import bpy, math, os
# 档案脊：一根薄而高的卡纸，四边带倒角，顶部一道细凹槽当标签位。
bpy.ops.wm.read_factory_settings(use_empty=True)

W, H, D = 0.34, 1.9, 1.1
bpy.ops.mesh.primitive_cube_add(size=1)
body = bpy.context.object
body.name = 'spine'
body.scale = (W, D, H)   # X 宽 / Y 厚 / Z 高（Blender 上轴是 Z）
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# 倒角：小圆角，2 段就够，边缘有高光才像实物
m = body.modifiers.new('bevel', 'BEVEL')
m.width = 0.012
m.segments = 2
m.limit_method = 'ANGLE'
bpy.ops.object.modifier_apply(modifier=m.name)

# 顶部标签凹槽：叠一个略窄的薄盒，用布尔差切出一道浅槽
bpy.ops.mesh.primitive_cube_add(size=1)
cut = bpy.context.object
cut.scale = (W * 0.86, D * 0.92, 0.045)
cut.location = (0, 0, H * 0.28)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
b = body.modifiers.new('groove', 'BOOLEAN')
b.operation = 'DIFFERENCE'
b.object = cut
bpy.ops.object.modifier_apply(modifier=b.name)
bpy.data.objects.remove(cut, do_unlink=True)

# 平滑着色：Blender 4.1+ 把自动平滑改成了操作符，老 API 已移除。
# 拿不到就退回平面着色——倒角本身已经有两段，硬边也不难看。
bpy.context.view_layer.objects.active = body
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
try:
    bpy.ops.object.shade_auto_smooth(angle=math.radians(45))
except Exception as e:
    print('auto smooth unavailable:', type(e).__name__)

body.select_set(True)
out = 'D:/WorkBuddy_cache/2026-10-31-20-54-55/class-schedule-web/web3d/models/spine.glb'
bpy.ops.export_scene.gltf(
    filepath=out, export_format='GLB', use_selection=True,
    export_apply=True, export_yup=True,
    export_normals=True, export_tangents=False,
    export_materials='NONE', export_cameras=False, export_lights=False,
)
print('GLB_OK', os.path.getsize(out), 'bytes; verts', len(body.data.vertices))
