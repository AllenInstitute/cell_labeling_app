import argparse
import logging
import os
from pathlib import Path
from typing import List, Union

import numpy as np
import pandas as pd
from cell_labeling_app.imaging_plane_artifacts import ArtifactFile
from flask import Flask
from sqlalchemy import desc

from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import LabelingJob, JobRegion

from cell_labeling_app.imaging_plane_artifacts import MotionBorder

from util import util

FIELD_OF_VIEW_DIMENSIONS = (512, 512)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Region:
    """A region in a field of view"""

    def __init__(self, x: int, y: int, width: int, height: int,
                 experiment_id: str):
        """
        :param x:
            Region upper left row value in array coordinates
        :param y:
            Region upper left col value in array coordinates
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
    """A class to sample regions from a field of view.

    Can be either sample experiments from LIMS or a file containing a list of
    pre-selected experiments.
    """
    def __init__(
        self,
        artifact_path: Union[str, Path],
        num_experiments: int = None,
        db_url: str = None,
        selected_experiments_path: str = None,
        num_regions_per_exp: int = 3,
        fov_divisor: int = 4,
        seed: int = None,
    ):
        """
        :param artifact_path
            Path to all possible labeling artifacts, containing imaging plane
            data and metadata
        :param num_experiments:
            Number of experiments to sample. Not used if selected_experiments
            is specified.
        :param db_url:
            Sqlalchemy database URL connection to LIMS. Not used if
            selected_experiments is specified.
        :param selected_experiments:
            Path specifying the location of a csv file containing pre-selected
            experiment ids. Column name for experiment is should be "exp_id".
        :param num_regions_per_exp:
            Number of regions per experiment to sample
        :param fov_divisor:
            The number of times to divide a field of view to get the region
            dimensions. Ie if the field of view is 512x512, and region_divisor
            is 4, the regions will be of size 128x128.
        :param seed:
            Seed for reproducibility
        """
        if (num_experiments is None or db_url is None) and \
           selected_experiments_path is None:
            raise ValueError("Please specify either of num_experiments and "
                             "db_url or selected experiments. Exiting.")
        if num_regions_per_exp > fov_divisor ** 2:
            raise ValueError("Number of requested regions per experiment "
                             "greater than number of regions created by "
                             "the fov_divisor. Reduce num_regions_per_exp "
                             "request.")
        self.db_url = db_url
        self._num_experiments = num_experiments
        self._num_regions_per_exp = num_regions_per_exp
        if not isinstance(artifact_path, Path):
            artifact_path = Path(artifact_path)
        self._artifact_path = artifact_path
        if selected_experiments_path is None:
            self._num_regions = num_experiments * num_regions_per_exp
            self._selected_experiments = None
        else:
            self._num_regions = \
                len(selected_experiments_path) * num_regions_per_exp
            self._selected_experiments = np.sort(pd.read_csv(
                selected_experiments_path)['exp_id'].to_numpy().astype(str))
        self._fov_divisor = fov_divisor
        self._seed = seed

    def sample(self,
               exclude_motion_border: bool = True) -> List[Region]:
        """
        Samples region candidates without replacement equally by experiment
        depth.
        :param exclude_motion_border:
            Whether to exclude regions outside of motion border
        :return:
        """
        rng = np.random.default_rng(seed=self._seed)

        if self._selected_experiments is None:
            experiment_ids = self._get_experiment_ids()
            exp_depth_df = self._retrieve_depths(experiment_ids)
            self._selected_experiments = self._sample_experiments(exp_depth_df,
                                                                  rng)

        regions = []
        for experiment_id in self._selected_experiments:
            exp_regions = self._get_all_regions_for_experiment(
                experiment_id=experiment_id,
                fov_divisor=self._fov_divisor,
                exclude_motion_border=exclude_motion_border
            )
            sub_regions: List[Region] = rng.choice(
                exp_regions, size=self._num_regions_per_exp)
            regions.extend(sub_regions)
        return regions

    def _sample_experiments(self,
                            exp_depth_df: pd.DataFrame,
                            rng: np.random.Generator) -> np.ndarray:
        """Sample experiments by equal likelihood in depth without replacement
        of experiment id.

        Parameters
        ----------
        exp_depth_df : pandas.DataFrame
            DataFrame containing columns id and depth.
        rng : numpy.random.Generator
            Seeded random number generator.

        Returns
        -------
        selected_experiments : numpy.ndarray, (N,)
            Sorted array of integer experiment ids that were selected
            randomly.
        """
        indexed_df = exp_depth_df.set_index('imaging_depth')
        depth_counts = exp_depth_df.groupby('imaging_depth').size()
        unique_depths = indexed_df.index.unique().sort_values()

        selected_experiments = set()
        if self._num_experiments > len(exp_depth_df):
            raise ValueError("Number of experiments requested to sample is "
                             "greater than the total number of experiments. "
                             "Please reduce the number of requested samples.")
        while len(selected_experiments) < self._num_experiments:
            depth = rng.choice(unique_depths, size=1)[0]
            if depth_counts.loc[depth] > 1:
                exp_id = rng.choice(indexed_df.loc[depth, 'exp_id'], size=1)[0]
            else:
                exp_id = indexed_df.loc[depth, 'exp_id']

            if exp_id in selected_experiments:
                continue
            selected_experiments.add(exp_id)

        return np.sort(list(selected_experiments))

    def _retrieve_depths(self, experiment_ids: List[int]) -> pd.DataFrame:
        """Query LIMS and retrieve experiment depths given their ids.

        Parameters
        ----------
        experiment_ids : list[int]
            List of integer experiment ids.

        Returns
        -------
        depths_df : pandas.DataFrame
            Pandas DataFrame containing columns id and imaging_depth.
        """
        query = "SELECT ophys_e.id as exp_id, ophys_e.imaging_depth_id, "
        query += "im_depth.id as im_id, im_depth.depth as imaging_depth "
        query += "FROM ophys_experiments ophys_e "
        query += "LEFT JOIN imaging_depths im_depth "
        query += "ON im_depth.id=ophys_e.imaging_depth_id "
        query += "WHERE ophys_e.id in ("
        query += ",".join([str(exp_id) for exp_id in experiment_ids])
        query += ")"

        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            data = pd.read_sql(query, conn)

        return data.sort_values('exp_id')

    def _get_motion_border_for_experiment(
            self,
            experiment_id: str) -> MotionBorder:
        """Gets the motion border for an experiment

        :return
            motion border
        """
        path = self._artifact_path / f'{experiment_id}_artifacts.h5'
        af = ArtifactFile(path=path)
        return af.motion_border

    def _get_all_regions_for_experiment(
            self,
            experiment_id: str,
            exclude_motion_border=True,
            fov_divisor=4
    ) -> List[Region]:
        """Gets list of all possible regions in a field of view
        by dividing the field of view into equally spaced regions

        :param experiment_id
            Experiment id
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
            mb = self._get_motion_border_for_experiment(
                experiment_id=experiment_id)
        else:
            mb = MotionBorder(
                left_side=0,
                right_side=0,
                top=0,
                bottom=0
            )

        within_border_fov_width = fov_width - mb.left_side - mb.right_side
        within_border_fov_height = fov_height - mb.top - mb.bottom

        region_width, region_height = (
            int(within_border_fov_width / fov_divisor),
            int(within_border_fov_height / fov_divisor))
        for row in range(mb.top,
                         fov_height - mb.bottom - region_height + 1,
                         region_height):
            for col in range(mb.left_side,
                             fov_width - mb.right_side - region_width + 1,
                             region_width):
                region = Region(x=row,
                                y=col,
                                width=region_width,
                                height=region_height,
                                experiment_id=experiment_id)
                res.append(region)
        return res

    def _get_experiment_ids(self):
        """Gets the list of experiment ids to sample from from the filename
        of the hdf5 files"""
        return util.get_experiment_ids(artifact_path=str(self._artifact_path))


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


if __name__ == '__main__':
    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument('--database_path', required=True,
                            help='Path to where the database should get '
                                 'created')
        parser.add_argument('--n',
                            help='Number of experiments to include in the '
                                 'labeling job',
                            type=int)
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
        parser.add_argument('--external_experiment_ids',
                            help='CSV file containing a column exp_id'
                                 'whose values are pre-sampled experiments. '
                                 'Overrides the "--n" argument.',
                            type=str)
        parser.add_argument('--n_regions_per_exp',
                            help='Number of regions per experiment to sample '
                                 'from each experiment.',
                            type=int,
                            default=3)
        parser.add_argument('--LIMS_user',
                            help='User name to use to connect to LIMS. '
                                 'Required if not using '
                                 'external_experiment_ids.',
                            type=str)
        parser.add_argument('--LIMS_password',
                            help='Password used to connect to LIMS Required '
                                 'if not using external_experiment_ids.',
                            type=str)
        parser.add_argument('--LIMS_host',
                            help='Name of LIMS host.',
                            default='limsdb2',
                            type=str)
        parser.add_argument('--LIMS_database',
                            help='Name of LIMS database.',
                            default='lims2',
                            type=str)
        parser.add_argument("--LIMS_port",
                            help='Port to connect to LIMS on.',
                            default=5432,
                            type=str)
        parser.add_argument('--exclude_motion_border', action='store_true',
                            default=True,
                            help='Whether to exclude the motion border when '
                                 'sampling regions')
        parser.add_argument('--artifact_files_dir', required=True,
                            help='Path to labeling artifact hdf5 files')
        parser.add_argument("--seed",
                            help='Seed value for the random number generator.',
                            default=1234,
                            type=int)
        args = parser.parse_args()

        if (args.LIMS_user is None or args.LIMS_password is None) and \
           args.external_experiment_ids is None:
            raise ValueError("No LIMS credentials set and no external "
                             "experiment is provided. Please specify one or "
                             "the other. Exiting.")

        artifacts_dir = Path(args.artifact_files_dir)
        database_path = Path(args.database_path)

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
        db.init_app(app)
        if not database_path.is_file():
            with app.app_context():
                db.create_all()
        app.app_context().push()
        db_url = f'postgresql+pg8000://{args.LIMS_user}:{args.LIMS_password}' \
                 f'@{args.LIMS_host}:{args.LIMS_port}/{args.LIMS_database}'

        sampler = RegionSampler(
            num_experiments=args.n,
            db_url=db_url,
            num_regions_per_exp=args.n_regions_per_exp,
            selected_experiments_path=args.external_experiment_ids,
            fov_divisor=args.fov_divisor,
            artifact_path=artifacts_dir,
            seed=args.seed)

        regions = sampler.sample(
            exclude_motion_border=args.exclude_motion_border,
        )
        populate_labeling_job(regions=regions)

    main()
