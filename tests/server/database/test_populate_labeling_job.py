import json
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
from cell_labeling_app.imaging_plane_artifacts import MotionBorder


class TestPopulateLabelingJob:
    """Tests region sampling and job creation"""
    def setup_class(self):
        self.artifacts_path = tempfile.TemporaryDirectory()
        self.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')
        self.config_fp = tempfile.NamedTemporaryFile('w', suffix='.py')

        self.motion_border = MotionBorder(
            top=30,
            bottom=30,
            left_side=30,
            right_side=28
        )

        for exp_id in (1,):
            exp_id_path = Path(self.artifacts_path.name)
            with h5py.File(exp_id_path / f'{exp_id}_artifacts.h5', 'w') as f:
                mb = {
                    'top': self.motion_border.top,
                    'right_side': self.motion_border.right_side,
                    'bottom': self.motion_border.bottom,
                    'left_side': self.motion_border.left_side
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
LOG_FILE = ''
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
            motion_border = self.motion_border
        else:
            motion_border = MotionBorder(
                top=0,
                bottom=0,
                left_side=0,
                right_side=0
            )
        self._regions_are_expected(regions=regions,
                                   motion_border=motion_border,
                                   fov_divisor=fov_divisor)

    @pytest.mark.parametrize('fov_divisor', (1, 2, 4))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    def test_get_all_regions_for_experiment(self, fov_divisor,
                                            exclude_motion_border):
        """tests that total number of regions is correct and all regions
        are as expected"""
        sampler = RegionSampler(num_regions=1, fov_divisor=fov_divisor,
                                artifact_path=self.artifacts_path.name)
        regions = sampler._get_all_regions_for_experiment(
            experiment_id='1', exclude_motion_border=exclude_motion_border,
            fov_divisor=fov_divisor)

        if exclude_motion_border:
            motion_border = self.motion_border
        else:
            motion_border = MotionBorder(
                top=0,
                bottom=0,
                left_side=0,
                right_side=0
            )
        self._regions_are_expected(regions=regions,
                                   motion_border=motion_border,
                                   fov_divisor=fov_divisor)
        assert len(regions) == fov_divisor ** 2

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
            motion_border = self.motion_border
        else:
            motion_border = MotionBorder(
                top=0,
                bottom=0,
                left_side=0,
                right_side=0
            )
        regions = db.session.query(JobRegion).all()
        self._regions_are_expected(regions=regions,
                                   motion_border=motion_border,
                                   fov_divisor=fov_divisor)

    @staticmethod
    def _regions_are_expected(regions: List[Region],
                              motion_border: MotionBorder,
                              fov_divisor: int):
        fov_dims = FIELD_OF_VIEW_DIMENSIONS

        for region in regions:
            assert region.x >= motion_border.left_side
            assert region.x + region.width <= fov_dims[0] - \
                   motion_border.right_side
            assert region.y >= motion_border.top
            assert region.y + region.height <= fov_dims[1] - \
                   motion_border.bottom

            assert region.width == \
                   int((fov_dims[0] -
                        motion_border.left_side - motion_border.right_side) /
                       fov_divisor)
            assert region.height == \
                   int((fov_dims[1] -
                        motion_border.top - motion_border.bottom) /
                       fov_divisor)
