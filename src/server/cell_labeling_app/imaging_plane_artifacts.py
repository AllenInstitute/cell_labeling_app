"""Module for retrieving imaging plane data"""

import json
from pathlib import Path
from typing import Union, List, Dict

import h5py
import numpy as np


class MotionBorder:
    """Motion border"""

    def __init__(self, left_side: int, right_side: int, top: int, bottom: int):
        """

        :param left_side:
            left side of motion border
        :param right_side:
            right side of motion border
        :param top:
            top of motion border
        :param bottom:
            bottom of motion border
        """
        self._left_side = left_side
        self._right_side = right_side
        self._top = top
        self._bottom = bottom

    @property
    def left_side(self):
        return self._left_side

    @property
    def right_side(self):
        return self._right_side

    @property
    def top(self):
        return self._top

    @property
    def bottom(self):
        return self._bottom


class ArtifactFile:
    """Class for reading artifacts from hdf5 file"""
    def __init__(self, path: Union[Path, str]):
        """
        :param path:
            Path to hdf5 file
        """
        self._path = path

    @property
    def experiment_id(self):
        return self._path.name.split('_')[0]

    @property
    def rois(self) -> List[dict]:
        with h5py.File(self._path, 'r') as f:
            return json.loads((f['rois'][()]))

    @property
    def motion_border(self) -> MotionBorder:
        with h5py.File(self._path, 'r') as f:
            mb = json.loads(f['motion_border'][()])
            mb = MotionBorder(left_side=int(mb['left_side']),
                              right_side=int(mb['right_side']),
                              top=int(mb['top']),
                              bottom=int(mb['bottom']))
        return mb

    def get_projection(self, projection_type: str) -> np.ndarray:
        with h5py.File(self._path, 'r') as f:
            if projection_type == 'max':
                dataset_name = 'max_projection'
            elif projection_type == 'average':
                dataset_name = 'avg_projection'
            elif projection_type == 'correlation':
                dataset_name = 'correlation_projection'
            else:
                raise ValueError('bad projection type')
            projection = f[dataset_name][:]

        if len(projection.shape) == 3:
            projection = projection[:, :, 0]
        projection = projection.astype('uint16')

        return projection

    def get_trace(
            self,
            is_user_added: bool,
            roi: Dict,
            roi_id: int) -> np.ndarray:
        """
        Gets trace. If roi_id not provided, gets trace at point from video
        :param roi_id:
            ROI id to retrieve trace for
        :param is_user_added:
            Whether the user added this roi or it was precomputed
        :param roi:
            Must include x, y, width, height

        :return: trace
        """
        if is_user_added:
            trace = self._get_trace_for_user_added_roi(roi=roi)
        else:
            with h5py.File(self._path, 'r') as f:
                trace = (f['traces'][str(roi_id)][()])

        return trace

    def _get_trace_for_user_added_roi(self, roi: Dict) -> np.ndarray:
        """Calculates a trace for roi by finding the mean pixel value in ROI
        across time"""
        x = roi['x']
        y = roi['y']
        width = roi['width']
        height = roi['height']
        with h5py.File(self._path, 'r') as f:
            sub_mov = f['video_data'][:, y:y+height, x:x+width]
            return sub_mov.reshape(sub_mov.shape[0], -1).mean(axis=-1)
