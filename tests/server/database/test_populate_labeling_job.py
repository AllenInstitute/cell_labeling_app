import json
import shutil
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

import h5py
import pytest
from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import JobRegion
from cell_labeling_app.database.populate_labeling_job import RegionSampler, \
    FIELD_OF_VIEW_DIMENSIONS, populate_labeling_job, Region
from cell_labeling_app.imaging_plane_artifacts import MotionBorder
from flask import Flask


class TestPopulateLabelingJob:
    """Tests region sampling and job creation"""
    def setup_class(self):
        self.artifacts_path = tempfile.TemporaryDirectory()
        self.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

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
        self.db_fp.close()
        shutil.rmtree(self.artifacts_path.name)

    def setup_method(self, method):
        self.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_fp.name}'
        db.init_app(app)
        with app.app_context():
            db.create_all()
        app.app_context().push()

    @pytest.mark.parametrize('fov_divisor', (1, 2, 4))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    def test_sampler(self,
                     fov_divisor,
                     exclude_motion_border):
        """tests that sampled regions are as expected"""
        with patch.object(RegionSampler,
                          '_sample_experiments',
                          return_value=(1,)), \
             patch.object(RegionSampler,
                          '_retrieve_depths',
                          return_value=MagicMock(spec=pd.DataFrame)):
            sampler = RegionSampler(num_experiments=1,
                                    num_regions_per_exp=1,
                                    fov_divisor=fov_divisor,
                                    db_url='',
                                    artifact_path=self.artifacts_path.name)
            regions = sampler.sample(
                exclude_motion_border=exclude_motion_border,
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

    def test_regions_sampled_without_replacement(self):
        """tests that regions are sampled without replacement"""
        with patch.object(RegionSampler,
                          '_sample_experiments',
                          return_value=(1,)), \
             patch.object(RegionSampler,
                          '_retrieve_depths',
                          return_value=MagicMock(spec=pd.DataFrame)):
            sampler = RegionSampler(num_experiments=1,
                                    num_regions_per_exp=256**2,
                                    fov_divisor=256,
                                    db_url='',
                                    artifact_path=self.artifacts_path.name)
            regions = sampler.sample()
        region_metas = [(region.x, region.y, region.width, region.height)
                        for region in regions]
        assert len(set(region_metas)) == len(region_metas)


    @pytest.mark.parametrize('fov_divisor', (1, 2, 4))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    def test_get_all_regions_for_experiment(self, fov_divisor,
                                            exclude_motion_border):
        """tests that total number of regions is correct and all regions
        are as expected"""
        sampler = RegionSampler(num_experiments=1,
                                num_regions_per_exp=1,
                                fov_divisor=fov_divisor,
                                db_url='',
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

    @pytest.mark.parametrize('fov_divisor', (1, 2, 4))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    def test_pre_sampled_ids(self,
                             fov_divisor,
                             exclude_motion_border):
        """tests that sampled regions are as expected"""
        csv_file = tempfile.mkstemp()
        id_df = pd.DataFrame(data={"exp_id": (1,)})
        id_df.to_csv(csv_file[1])

        with patch.object(RegionSampler,
                          '_retrieve_depths',
                          return_value=MagicMock(spec=pd.DataFrame)):
            sampler = RegionSampler(selected_experiments_path=csv_file[1],
                                    num_regions_per_exp=1,
                                    fov_divisor=fov_divisor,
                                    db_url='',
                                    artifact_path=self.artifacts_path.name)
            regions = sampler.sample(
                exclude_motion_border=exclude_motion_border,
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

    def test_raises(self):
        with pytest.raises(ValueError, match=r'Please specify either .*'):
            RegionSampler(num_regions_per_exp=1,
                          artifact_path=self.artifacts_path.name)

        with pytest.raises(ValueError, match=r'Number of requested .*'):
            RegionSampler(num_experiments=1,
                          db_url='',
                          num_regions_per_exp=3,
                          fov_divisor=1,
                          artifact_path=self.artifacts_path.name)

    def test_depth_exp_id_sampling(self):
        """Test that the sampling algorithm selects the expected experiments.
        """
        data_frame = pd.DataFrame(data={"exp_id": [1, 2, 3, 4],
                                        "imaging_depth": [10, 10, 10, 12],
                                        "im_id": [7, 8, 9, 10]})

        rng = np.random.default_rng(1234)
        sampler = RegionSampler(artifact_path=self.artifacts_path.name,
                                num_experiments=3,
                                db_url='',
                                num_regions_per_exp=1,
                                fov_divisor=2)
        selected_experiments = sampler._sample_experiments(
            data_frame,
            rng)
        np.testing.assert_equal(selected_experiments, [1, 3, 4])

    @pytest.mark.parametrize('num_regions', (6, 7))
    @pytest.mark.parametrize('exclude_motion_border', (True, False))
    @pytest.mark.parametrize('fov_divisor', (4,))
    def test_create_labeling_job(self, num_regions, exclude_motion_border,
                                 fov_divisor):
        """tests that region entries populated in db are as expected"""
        with patch.object(RegionSampler,
                          '_sample_experiments',
                          return_value=(1,)), \
             patch.object(RegionSampler,
                          '_retrieve_depths',
                          return_value=MagicMock(spec=pd.DataFrame)):
            sampler = RegionSampler(num_experiments=1,
                                    num_regions_per_exp=num_regions,
                                    fov_divisor=fov_divisor,
                                    db_url='',
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
            assert region.x >= motion_border.top
            assert region.x + region.height <= fov_dims[1] - \
                   motion_border.bottom
            assert region.y >= motion_border.left_side
            assert region.y + region.width <= fov_dims[1] - \
                   motion_border.right_side

            assert region.width == \
                   int((fov_dims[0] -
                        motion_border.left_side - motion_border.right_side) /
                       fov_divisor)
            assert region.height == \
                   int((fov_dims[1] -
                        motion_border.top - motion_border.bottom) /
                       fov_divisor)
