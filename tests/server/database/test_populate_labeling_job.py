import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import List

import h5py
import pytest
from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import JobRegion
from cell_labeling_app.main import create_app
from cell_labeling_app.database.populate_labeling_job import RegionSampler, \
    FIELD_OF_VIEW_DIMENSIONS, populate_labeling_job, Region


class TestPopulateLabelingJob:
    """Tests region sampling and job creation"""
    def setup_class(self):
        self.artifacts_path = tempfile.TemporaryDirectory()
        self.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')
        self.config_fp = tempfile.NamedTemporaryFile('w', suffix='.py')

        self.motion_border_x = 10
        self.motion_border_y = 20

        for exp_id in (1,):
            exp_id_path = Path(self.artifacts_path.name)
            with h5py.File(exp_id_path / f'{exp_id}_artifacts.h5', 'w') as f:
                mb = {
                    'top': self.motion_border_y,
                    'right_side': self.motion_border_x,
                    'bottom': self.motion_border_y,
                    'left_side': self.motion_border_x
                }
                mb = json.dumps(mb)
                f.create_dataset('motion_border', data=mb)

    def teardown_class(self):
        self.config_fp.close()
        self.db_fp.close()
        shutil.rmtree(self.artifacts_path.name)

    def setup_method(self, method):
        self.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')
        self.config_fp = tempfile.NamedTemporaryFile('w', suffix='.py')

        config = f'''
SQLALCHEMY_DATABASE_URI = f'sqlite:///{self.db_fp.name}'
SESSION_SECRET_KEY = 1
SQLALCHEMY_TRACK_MODIFICATIONS = False
        '''
        self.config_fp.write(config)
        self.config_fp.seek(0)

        app = create_app(config_file=Path(self.config_fp.name))
        with app.app_context():
            db.create_all()
        app.app_context().push()

    @pytest.mark.parametrize('fov_divisor', (1, 2, 4))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    def test_sampler(self, fov_divisor, exclude_motion_border):
        """tests that sampled regions are as expected"""
        sampler = RegionSampler(num_regions=1, fov_divisor=fov_divisor,
                                artifact_path=self.artifacts_path.name)
        regions = sampler.sample(
            exclude_motion_border=exclude_motion_border
        )
        if exclude_motion_border:
            motion_border_x = self.motion_border_x
            motion_border_y = self.motion_border_y
        else:
            motion_border_x = 0
            motion_border_y = 0
        self._regions_are_expected(regions=regions,
                                   motion_border_y=motion_border_y,
                                   motion_border_x=motion_border_x,
                                   fov_divisor=fov_divisor)

    @pytest.mark.parametrize('num_regions', (6, 7))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    @pytest.mark.parametrize('fov_divisor', (4,))
    def test_create_labeling_job(self, num_regions, exclude_motion_border,
                                 fov_divisor):
        """tests that region entries populated in db are as expected"""
        sampler = RegionSampler(num_regions=num_regions,
                                fov_divisor=fov_divisor,
                                artifact_path=self.artifacts_path.name)
        regions = sampler.sample(
            exclude_motion_border=exclude_motion_border
        )
        populate_labeling_job(regions=regions)

        num_added = db.session.query(JobRegion).filter_by(
            job_id=1).count()
        assert num_added == num_regions

        if exclude_motion_border:
            motion_border_x = self.motion_border_x
            motion_border_y = self.motion_border_y
        else:
            motion_border_x = 0
            motion_border_y = 0
        regions = db.session.query(JobRegion).all()
        self._regions_are_expected(regions=regions,
                                   motion_border_x=motion_border_x,
                                   motion_border_y=motion_border_y,
                                   fov_divisor=fov_divisor)

    @staticmethod
    def _regions_are_expected(regions: List[Region],
                              motion_border_x: int,
                              motion_border_y: int,
                              fov_divisor: int):
        fov_dims = FIELD_OF_VIEW_DIMENSIONS

        for region in regions:
            assert region.x >= motion_border_x
            assert region.x + region.width <= fov_dims[0] - \
                   motion_border_x
            assert region.y >= motion_border_y
            assert region.y + region.height <= fov_dims[1] - \
                   motion_border_y

            assert region.width == int((fov_dims[0] - motion_border_x * 2) /
                                       fov_divisor)
            assert region.height == int((fov_dims[1] - motion_border_y * 2) /
                                        fov_divisor)
