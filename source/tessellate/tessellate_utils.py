import torch
import math
import numpy as np
import pandas as pd
from torch.nn.functional import conv2d
from typing import Optional


def get_bounding_box(array: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """
    Returns minimum and maximum row and column index for box around
    non-zero elements.

    Args:
        array: array for which the bounding box enclosing all non-zero elements
            should be found.
    Returns:
        rmin: smallest row index with non-zero element.
        rmax: largest row index with non-zero element.
        cmin: smallest column index with non-zero element.
        cmax: largest column index with non-zero element.
    """
    rows = np.any(array, axis=1)
    cols = np.any(array, axis=0)
    # check if there are any non-zero elements
    if sum(rows) == 0 or sum(cols) == 0:
        return None

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    return rmin, rmax, cmin, cmax


def tessellate(
    segmentations: dict,
    config: dict,
    scaling_factor: float = 1.0,
) -> dict[int, list[tuple[tuple[int, int], tuple[int, int]]]]:
    """
    Extracts tiles from a segmentation.

    Args:
        segmentation: segmentation of the whole-slide image as (height, width).
        scaling_factor: scaling factor between the extraction level and the highest magnification level.

    Returns:
        tile_information: list containing the location and shape of the tiles for each cross-section.
    """

    # combine all segmentations
    union_of_all_segmentations = np.zeros(
        next(iter(segmentations.values())).shape,
        dtype=np.uint8,
    )
    for segmentation in segmentations.values():
        union_of_all_segmentations = np.logical_or(
            union_of_all_segmentations, segmentation
        )

    segmentation_width, segmentation_height = (
        union_of_all_segmentations.shape[1],
        union_of_all_segmentations.shape[0],
    )

    patch_size = [int(dim / scaling_factor) for dim in config["patch_dimensions"]]
    patch_width, patch_height = patch_size[1], patch_size[0]

    if isinstance(union_of_all_segmentations, torch.Tensor):
        union_of_all_segmentations = union_of_all_segmentations.numpy()

    # check if the shape is not larger than the segmentation
    if patch_width > segmentation_width or patch_height > segmentation_height:
        raise ValueError(
            "Argument for `shape` exceeds the height and/or width of the segmentation.",
        )

    # set the stride equal to the shape if it is None
    stride = (
        config["stride"]
        if "stride" in config.keys() and config["stride"] is not None
        else patch_size
    )
    horizontal_stride, vertical_stride = stride[1], stride[0]

    # calulate the maximum number of patches that fit inside the image
    max_horizontal_patches = (segmentation_width - patch_width) // horizontal_stride + 1
    max_vertical_patches = (segmentation_height - patch_height) // vertical_stride + 1

    # initialize dictionary to store tile location and shapes

    bounding_box = get_bounding_box(union_of_all_segmentations)

    if bounding_box is None:
        return None

    # create a boundix box and calculate the width and height
    (
        top,
        bottom,
        left,
        right,
    ) = bounding_box

    bounding_box_width = right - left
    bounding_box_height = bottom - top

    # determine how many patches are needed in both dimensions to completely cover the bounding box
    # two cases are possible:
    # 1. the bounding box is smaller than the patch size -> default to one patch
    # 2. the bounding box is larger than the patch size -> calculate the number of patches needed
    horizontal_patches_needed_to_cover_bounding_box = (
        max(math.ceil((bounding_box_width - patch_width) / horizontal_stride), 0) + 1
    )
    vertical_patches_needed_to_cover_bounding_box = (
        max(math.ceil((bounding_box_height - patch_height) / vertical_stride), 0) + 1
    )

    # the number of patches should never be more than the maximum number of patches
    # that fit inside the image
    horizontal_patches = min(
        horizontal_patches_needed_to_cover_bounding_box, max_horizontal_patches
    )
    vertical_patches = min(
        vertical_patches_needed_to_cover_bounding_box, max_vertical_patches
    )

    # calculate the width and height spanned by the patches
    width_spanned_by_horizontal_patches = (
        horizontal_patches - 1
    ) * horizontal_stride + patch_width
    height_spanned_by_vertical_patches = (
        vertical_patches - 1
    ) * vertical_stride + patch_height

    # Align the center of the patches with the center of the bounding box
    horizontal_shift = (bounding_box_width - width_spanned_by_horizontal_patches) // 2
    left_margin = left + horizontal_shift

    vertical_shift = (bounding_box_height - height_spanned_by_vertical_patches) // 2
    top_margin = top + vertical_shift

    # Ensure that no patches fall outside the segmentation
    if left_margin < 0:
        left_margin = 0
    if left_margin + width_spanned_by_horizontal_patches > segmentation_width:
        horizontal_shift = (
            left_margin + width_spanned_by_horizontal_patches - segmentation_width
        )
        left_margin -= horizontal_shift
    if top_margin < 0:
        top_margin = 0
    if top_margin + height_spanned_by_vertical_patches > segmentation_height:
        vertical_shift = (
            top_margin + height_spanned_by_vertical_patches - segmentation_height
        )
        top_margin -= vertical_shift

    # loop through all segmentations and extract tiles
    tile_information = pd.DataFrame(
        columns=list(segmentations.keys()),
        index=pd.MultiIndex(levels=[[], []], codes=[[], []], names=["x", "y"]),
    )
    tile_information.index.name = "origin_coordinates"

    for segmentation_name, segmentation in segmentations.items():
        # crop the segmentation and prepare for convolution
        crop = segmentation[
            top_margin : top_margin + height_spanned_by_vertical_patches,
            left_margin : left_margin + width_spanned_by_horizontal_patches,
        ][None, None, ...].astype(np.float32)
        # define average filter
        filter = (torch.ones(patch_size) / np.prod(patch_size))[None, None, ...]
        # convolve crop with filter
        filtered_crop = conv2d(
            torch.from_numpy(crop),
            weight=filter,
            bias=None,
            stride=stride,
            padding="valid",
        )[0, 0, ...].numpy()
        # find the region to extract tiles from

        extraction_region = np.where(
            filtered_crop >= config["min_tissue_fraction"], 1, 0
        )

        # find the indices of the tiles that exceed the minimum faction of tissue
        indices = np.nonzero(extraction_region)

        # loop over indices to get all (top left) tile locations
        for x, y in zip(indices[1], indices[0]):
            origin = (
                int(left_margin + x * horizontal_stride),
                int(top_margin + y * vertical_stride),
            )

            # add information about the location and shape of the tiles
            # to the dataframe
            tile_information.loc[origin, segmentation_name] = True

    tile_information = tile_information.fillna(False)

    return tile_information
