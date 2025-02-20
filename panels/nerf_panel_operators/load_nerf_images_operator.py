import bpy

from turbo_nerf.blender_utility.blender_ui_utility import switch_to_turbo_nerf_renderer
from turbo_nerf.blender_utility.obj_type_utility import get_active_nerf_obj
from turbo_nerf.constants import NERF_ITEM_IDENTIFIER_ID
from turbo_nerf.utility.nerf_manager import NeRFManager

class LoadNeRFImagesOperator(bpy.types.Operator):
    bl_idname = "turbo_nerf.load_nerf_images"
    bl_label = "Load Images"
    
    @classmethod
    def poll(cls, context):
        nerf_obj = get_active_nerf_obj(context)
        has_nerf = nerf_obj is not None
        return has_nerf and NeRFManager.can_load_images()
    
    def execute(self, context):
        nerf_obj = get_active_nerf_obj(context)
        nerf_id = nerf_obj[NERF_ITEM_IDENTIFIER_ID]

        NeRFManager.prepare_for_training(nerf_id)

        switch_to_turbo_nerf_renderer(context)
        return {'FINISHED'}
