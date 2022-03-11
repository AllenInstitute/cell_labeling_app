"""Module for retrieving imaging plane data"""

import json
from pathlib import Path
from typing import Union, List, Optional

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

    def get_trace(self, roi_id: Optional[str] = None,
                  point: Optional[List] = None) -> np.ndarray:
        """
        Gets trace. If roi_id not provided, gets trace at point from video
        :param roi_id:
            ROI id to retrieve trace for
        :param point:
            point to retrieve trace for
        :return:
        """
        if roi_id is not None and point is not None:
            raise ValueError('Must provide roi_id or point, not both')

        if roi_id is not None:
            with h5py.File(self._path, 'r') as f:
                trace = (f['traces'][roi_id][()])
        elif point is not None:
            trace = self._get_trace_for_point(point=point)
        else:
            raise ValueError('Must provide roi_id or point')
        return trace

    def _get_trace_for_point(self, point: List) -> np.ndarray:
        x, y = point
        with h5py.File(self._path, 'r') as f:
            return f['video_data'][:, y, x]
