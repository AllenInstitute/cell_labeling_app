import argparse
import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
from sqlalchemy import desc

from server.database.database import db
from server.database.schemas import LabelingJob, JobRegion
from server.main import create_app

FIELD_OF_VIEW_DIMENSIONS = (512, 512)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Region:
    """A region in a field of view"""

    def __init__(self, x: int, y: int, width: int, height: int,
                 experiment_id: str):
        """
        :param x:
            Region upper left x value in fov coordinates
        :param y:
            Region upper left y value in fov coordinates
        :param width
            Region width
        :param height
            region height
        :param
            The experiment id the region belongs to
        """
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._experiment_id = experiment_id

    @property
    def x(self) -> int:
        return self._x

    @property
    def y(self) -> int:
        return self._y

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def experiment_id(self) -> str:
        return self._experiment_id


class RegionSampler:
    """A class to sample regions from a field of view"""
    def __init__(
        self,
        num_regions: int,
        fov_divisor=4,
        seed=None
    ):
        """
        :param num_regions:
            Number of regions to sample
        :param fov_divisor:
            The number of times to divide a field of view to get the region
            dimensions. Ie if the field of view is 512x512, and region_divisor
            is 4, the regions will be of size 128x128.
        :param seed:
            Seed for reproducibility
        """
        self._num_regions = num_regions
        self._fov_divisor = fov_divisor
        self._seed = seed

    def sample(self,
               experiment_ids: List[str],
               motion_correction_path: Optional[Path],
               exclude_motion_border=True):
        """
        Samples region candidates without replacement
        :param experiment_ids
            List of experiment ids to sample from
        :param motion_correction_path:
            Path to motion correction output. Used for excluding regions
            outside of motion border. Required if exclude_motion_border is True
        :param exclude_motion_border:
            Whether to exclude regions outside of motion border
        :return:
        """
        if exclude_motion_border and motion_correction_path is None:
            raise ValueError('motion_correction_path required if '
                             'exclude_motion_border is True')

        all_regions = []
        for experiment_id in experiment_ids:
            regions = self._get_all_regions_for_experiment(
                experiment_id=experiment_id,
                motion_correction_path=motion_correction_path,
                fov_divisor=self._fov_divisor,
                exclude_motion_border=exclude_motion_border
            )
            for region in regions:
                all_regions.append(region)

        rng = np.random.default_rng(seed=self._seed)
        regions: List[Region] = \
            rng.choice(all_regions, size=self._num_regions,
                       replace=False)
        return regions

    @staticmethod
    def _get_motion_border_for_experiment(
            experiment_id: str,
            motion_correction_path: Path) -> Tuple[int, int]:
        """Gets the motion border for an experiment

        :return
            motion border x, y values
        """
        registration_output = motion_correction_path / f'{experiment_id}' / \
            f'{experiment_id}_rigid_motion_transform.csv'
        df = pd.read_csv(registration_output)
        border_x = df['x'].abs().max()
        border_y = df['y'].abs().max()
        return border_x, border_y

    def _get_all_regions_for_experiment(
            self,
            experiment_id: str,
            motion_correction_path: Path,
            exclude_motion_border=True,
            fov_divisor=4
    ) -> List[Region]:
        """Gets list of all possible regions in a field of view
        by dividing the field of view into equally spaced regions

        :param experiment_id
            Experiment id
        :param motion_correction_path
            Path to motion correction output
        :param exclude_motion_border
            Whether to exclude the motion border when sampling regions
        :param fov_divisor
            The number of times to divide a field of view to get the region
            dimensions. Ie if the field of view is 512x512, and region_divisor
            is 4, the regions will be of size 128x128.
        """
        res = []
        fov_width, fov_height = FIELD_OF_VIEW_DIMENSIONS

        if exclude_motion_border:
            border_offset_x, border_offset_y = \
                self._get_motion_border_for_experiment(
                    experiment_id=experiment_id,
                    motion_correction_path=motion_correction_path)
        else:
            border_offset_x, border_offset_y = 0, 0

        within_border_fov_width = fov_width - border_offset_x * 2
        within_border_fov_height = fov_height - border_offset_y * 2

        region_width, region_height = (int(within_border_fov_width /
                                           fov_divisor),
                                       int(within_border_fov_height /
                                           fov_divisor))

        for y in range(border_offset_y,
                       fov_height - border_offset_y,
                       region_height):
            for x in range(border_offset_x,
                           fov_width - border_offset_x,
                           region_width):
                region = Region(x=x,
                                y=y,
                                width=region_width,
                                height=region_height,
                                experiment_id=experiment_id)
                res.append(region)
        return res


def populate_labeling_job(regions: List[Region]):
    """
    Creates a new labeling job
    :param regions
        List of regions to add to the labeling job
    :return:
        None. Inserts records into the DB
    """
    job = LabelingJob()
    db.session.add(job)

    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]

    for region in regions:
        job_region = JobRegion(job_id=job_id,
                               experiment_id=region.experiment_id,
                               x=region.x, y=region.y, width=region.width,
                               height=region.height)
        db.session.add(job_region)

    db.session.commit()

    num_added = db.session.query(JobRegion).filter_by(job_id=job_id).count()
    logger.info(f'Number of regions added to labeling job: {num_added}')


def _get_experiment_ids(motion_correction_path: Path):
    """Gets the list of experiment ids to sample from from the list of
    experiment ids in the motion correction directory"""
    experiments = os.listdir(motion_correction_path)
    return experiments


if __name__ == '__main__':
    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument('--config_path', required=True,
                            help='Path to app config')
        parser.add_argument('--n', required=True,
                            help='Number of regions to include in the '
                                 'labeling job')
        parser.add_argument('--fov_divisor',
                            help='Amount by which the field of view '
                                 'is divided to obtain the region '
                                 'dimensions. Ie if the field of view is '
                                 '512x512 and fov_divisor is 4, this will '
                                 'divide each dimension by 4 to yield regions '
                                 'of size 128x128. If exclude_motion_border '
                                 'is True, then region divisor will divide '
                                 'up the area within the motion border.',
                            type=int, default=4)
        parser.add_argument('--exclude_motion_border', action='store_true',
                            default=True,
                            help='Whether to exclude the motion border when '
                                 'sampling regions')
        parser.add_argument('--motion_correction_path', required=True,
                            help='Path to motion correction output. Used for '
                                 'sampling within motion border and for '
                                 'extracting list of all experiment ids.')
        args = parser.parse_args()
        n = int(args.n)

        config_path = Path(args.config_path)
        motion_correction_path = Path(args.motion_correction_path) if \
            args.motion_correction_path else None

        app = create_app(config_file=config_path)
        if not Path(app.config['SQLALCHEMY_DATABASE_URI']
                    .replace('sqlite:///', '')).is_file():
            with app.app_context():
                db.create_all()
        app.app_context().push()

        sampler = RegionSampler(num_regions=n, fov_divisor=args.fov_divisor)
        experiment_ids = _get_experiment_ids(
            motion_correction_path=motion_correction_path)
        regions = sampler.sample(
            experiment_ids=experiment_ids,
            motion_correction_path=motion_correction_path,
            exclude_motion_border=args.exclude_motion_border
        )
        populate_labeling_job(regions=regions)

    main()
