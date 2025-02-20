import bpy
import math
import numpy as np

from copy import copy
from turbo_nerf.blender_utility.obj_type_utility import is_nerf_obj_type

from turbo_nerf.utility.math import bl2nerf_mat
from turbo_nerf.utility.nerf_manager import NeRFManager

from turbo_nerf.utility.pylib import PyTurboNeRF as tn

from turbo_nerf.constants import (
    CAM_TYPE_BLENDER_PERSPECTIVE,
    CAM_TYPE_TRAIN_OPENCV,
    CAMERA_CX_ID,
    CAMERA_CY_ID,
    CAMERA_FAR_ID,
    CAMERA_FL_X_ID,
    CAMERA_FL_Y_ID,
    CAMERA_IMAGE_H_ID,
    CAMERA_IMAGE_W_ID,
    CAMERA_K1_ID,
    CAMERA_K2_ID,
    CAMERA_K3_ID,
    CAMERA_NEAR_ID,
    CAMERA_P1_ID,
    CAMERA_P2_ID,
    CAMERA_SHOW_IMAGE_PLANES_ID,
    OBJ_TYPE_TRAIN_CAMERA,
    RENDER_CAM_TYPE_ID,
    RENDER_CAM_TYPE_PERSPECTIVE,
    RENDER_CAM_TYPE_SPHERICAL_QUADRILATERAL,
    RENDER_CAM_TYPE_QUADRILATERAL_HEXAHEDRON
)

def bl2nerf_fl(cam_data: bpy.types.Camera, output_dimensions: tuple[int, int]) -> float:
    (nerf_w, nerf_h) = output_dimensions
    # calculate focal len
    bl_sw = cam_data.sensor_width
    bl_sh = cam_data.sensor_height
    bl_f  = cam_data.lens

    # get blender sensor size in pixels
    px_w: float
    # px_h: float
    
    if cam_data.sensor_fit == 'AUTO':
        bl_asp = 1.0
        nerf_asp = nerf_h / nerf_w

        if nerf_asp > bl_asp:
            px_w = nerf_h / bl_asp
            # px_h = nerf_h
        else:
            px_w = nerf_w
            # px_h = nerf_w * bl_asp

    elif cam_data.sensor_fit == 'HORIZONTAL':
        px_w = nerf_w
        # px_h = nerf_w * bl_sh / bl_sw

    elif cam_data.sensor_fit == 'VERTICAL':
        px_w = nerf_h * bl_sw / bl_sh
        # px_h = nerf_h
    
    
    # focal length in pixels
    px_f = bl_f / bl_sw * px_w

    return px_f

def bl2nerf_shift(context: bpy.types.Context, cam_data: bpy.types.Camera, fl_x: float, img_dims: tuple[int, int]):
    render = context.scene.render
    out_res_x = render.resolution_x
    out_res_y = render.resolution_y
    cam_fl = bl2nerf_fl(cam_data, (out_res_x, out_res_y))

    cam_angle_x = 2.0 * math.atan2(0.5 * out_res_x, cam_fl)
    
    cam_res_x = 2.0 * fl_x * math.tan(0.5 * cam_angle_x)
    cam_res_y = out_res_y / out_res_x * cam_res_x

    horizontal_fit = cam_data.sensor_fit == 'HORIZONTAL' or (cam_data.sensor_fit == 'AUTO' and cam_res_x > cam_res_y)

    if horizontal_fit:
        u = cam_res_x / img_dims[0]
        v = cam_res_x / img_dims[1]
    else:
        u = cam_res_y / img_dims[0]
        v = cam_res_y / img_dims[1]
    
    return u * cam_data.shift_x, v * cam_data.shift_y

# converts aperture fstop to aperture size
def bl2nerf_fstop2size(fstop: float) -> float:
    return 1.0 / (2.0 * fstop)

def bl2nerf_cam_regionview3d(
    region_view_3d: bpy.types.RegionView3D,
    img_dims: tuple[int, int],
    context: bpy.types.Context
) -> tn.Camera:
    # P
    projection_matrix = np.array(region_view_3d.window_matrix)
    # V 
    view_matrix = np.array(region_view_3d.view_matrix.inverted())
    # P * V
    # perspective_matrix = np.array(region_view_3d.perspective_matrix)

    bl_camera_matrix = tn.Transform4f(view_matrix)

    # is_perspective = region_view_3d.is_perspective

    # look into region_view_3d.view_persepctive
    # get focal length
    fl_x = 0.5 * img_dims[0] * projection_matrix[0, 0]
    fl_y = 0.5 * img_dims[1] * projection_matrix[1, 1]

    near: float
    far: float

    shift_x: float = 0.0
    shift_y: float = 0.0

    if region_view_3d.view_perspective == 'CAMERA':
        cam_data: bpy.types.Camera = context.scene.camera.data
        near = cam_data.clip_start
        far = cam_data.clip_end
        shift_x, shift_y = bl2nerf_shift(context, cam_data, fl_x, img_dims)

    else:
        view = context.space_data
        near = view.clip_start
        far = view.clip_end

    return tn.Camera(
        resolution=img_dims,
        near=near,
        far=far,
        focal_length=(fl_x, fl_y),
        shift=(shift_x, -shift_y),
        principal_point=(0.5 * img_dims[0], 0.5 * img_dims[1]),
        transform=bl_camera_matrix.from_nerf()
    )

def bl2nerf_cam_train(cam_obj: bpy.types.Object):
    c2w = np.array(cam_obj.matrix_world)
    transform = tn.Transform4f(c2w).from_nerf()

    dist_params = tn.DistortionParams(
        k1=cam_obj[CAMERA_K1_ID],
        k2=cam_obj[CAMERA_K2_ID],
        k3=cam_obj[CAMERA_K3_ID],
        p1=cam_obj[CAMERA_P1_ID],
        p2=cam_obj[CAMERA_P2_ID]
    )

    cam = tn.Camera(
        resolution=(cam_obj[CAMERA_IMAGE_W_ID], cam_obj[CAMERA_IMAGE_H_ID]),
        near=cam_obj[CAMERA_NEAR_ID],
        far=cam_obj[CAMERA_FAR_ID],
        focal_length=(cam_obj[CAMERA_FL_X_ID], cam_obj[CAMERA_FL_Y_ID]),
        shift=(0, 0),
        principal_point=(cam_obj[CAMERA_CX_ID], cam_obj[CAMERA_CY_ID]),
        transform=transform,
        dist_params=dist_params
    )

    cam.show_image_planes = cam_obj[CAMERA_SHOW_IMAGE_PLANES_ID]

    return cam

def bl2nerf_cam_perspective(context: bpy.types.Context, cam_obj: bpy.types.Object, img_dims: tuple[int, int]):
    view_matrix = np.array(cam_obj.matrix_world)

    bl_camera_matrix = tn.Transform4f(view_matrix)

    # look into region_view_3d.view_perspective
    # get focal length

    cam_data: bpy.types.Camera = cam_obj.data
    fl_x = bl2nerf_fl(cam_data, img_dims)
    fl_y = fl_x

    shift_x, shift_y = bl2nerf_shift(context, cam_data, fl_x, img_dims)

    return tn.Camera(
        resolution=img_dims,
        near=cam_data.clip_start,
        far=cam_data.clip_end,
        focal_length=(fl_x, fl_y),
        shift=(shift_x, shift_y),
        principal_point=(0.5 * img_dims[0], 0.5 * img_dims[1]),
        transform=bl_camera_matrix.from_nerf()
    )

def bl2nerf_cam(
    source: bpy.types.RegionView3D | bpy.types.Object,
    img_dims: tuple[int, int],
    context: bpy.types.Context = None
) -> tn.Camera:
    
    if context is None:
        context = bpy.context
    
    if isinstance(source, bpy.types.RegionView3D):
        return bl2nerf_cam_regionview3d(source, img_dims, context)
    
    elif isinstance(source, bpy.types.Object):
        camera_model = CAM_TYPE_BLENDER_PERSPECTIVE
        
        # elif RENDER_CAM_TYPE_ID in source:
        #     camera_model = source[RENDER_CAM_TYPE_ID]
        
        if camera_model not in CAM_TYPE_DECODERS:
            camera_model = CAM_TYPE_BLENDER_PERSPECTIVE
        
        decoder = CAM_TYPE_DECODERS[camera_model]

        return decoder(context, source, img_dims)
    else:
        print(f"INVALID CAMERA SOURCE: {source}")
        return None

def camera_with_flipped_y(cam: tn.Camera) -> tn.Camera:
    yflip = np.array(cam.transform)
    yflip[:, 1] *= -1.0
    transform = tn.Transform4f(yflip)

    shift_x, shift_y = cam.shift
    shift_y *= -1.0

    return tn.Camera(
        resolution=cam.resolution,
        near=cam.near,
        far=cam.far,
        focal_length=cam.focal_length,
        principal_point=cam.principal_point,
        shift=(shift_x, shift_y),
        transform=transform,
        dist_params=cam.dist_params
    )

CAM_TYPE_DECODERS = {
    CAM_TYPE_BLENDER_PERSPECTIVE: bl2nerf_cam_perspective
}
