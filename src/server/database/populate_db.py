import argparse
import os
import re
from pathlib import Path
from typing import List, Tuple

import numpy as np
from flask import Flask
from sqlalchemy import desc

from src.server.database.database import db
from src.server.database.schemas import LabelingJob, JobRegion
from src.server.main import create_app

FIELD_OF_VIEW_DIMENSIONS = (512, 512)


class Region:
    """A region in a field of view"""
    def __init__(self, x: int, y: int):
        """
        :param x:
            Region upper left x value in fov coordinates
        :param y:
            Region upper left y value in fov coordinates
        """
        self._x = x
        self._y = y

    @property
    def x(self) -> int:
        return self._x

    @property
    def y(self) -> int:
        return self._y


def _get_all_experiments(artifact_dir: Path) -> List[str]:
    """
    Returns a list of all available experiments

    :param artifact_dir:
        Path to artifact hdf5 files
    :return:
        list of all available experiments
    """
    res = []
    experiments = os.listdir(artifact_dir)
    for experiment in experiments:
        experiment_id = re.match(r'\d+', experiment).group()
        res.append(experiment_id)
    return res


def _get_all_regions(
        region_dimensions: Tuple[int, int],
        border_offset: int) -> List[Region]:
    """Gets list of all possible regions in a field of view
    by evenly dividing the field of view into equally spaced regions
    :param region_dimensions:
        Region dimensions (width x height)
    :param border_offset
        Offset to apply so that regions are only sampled this distance away
        from the border
    """
    res = []
    fov_width, fov_height = FIELD_OF_VIEW_DIMENSIONS
    region_width, region_height = region_dimensions

    for y in range(border_offset, fov_height - border_offset, region_height):
        for x in range(border_offset, fov_width - border_offset, region_width):
            region = Region(x=x, y=y)
            res.append(region)
    return res


def _get_all_experiment_regions(
        artifact_dir: Path,
        region_dimensions: Tuple[int, int],
        border_offset: int) -> List[str]:
    """Returns list of all experiment-region combinations in string form
    :param artifact_dir:
        Path to artifact hdf5 files
    :param region_dimensions:
        Region dimensions (width x height)
    :param border_offset
        Offset to apply so that regions are only sampled this distance away
        from the border
    """
    experiments = _get_all_experiments(artifact_dir=artifact_dir)
    regions = _get_all_regions(region_dimensions=region_dimensions,
                               border_offset=border_offset)

    res = []
    for experiment in experiments:
        for region in regions:
            res.append(f'{experiment}_{region.x}_{region.y}')
    return res


def populate_labeling_job(app: Flask, db, n: int,
                          region_dimensions: Tuple[int, int],
                          border_offset: int):
    """
    Creates a new labeling job by randomly sampling n total regions from all
    available experiments
    :param app:
        The flask app
    :param db:
        The database
    :param n:
        Number of regions in this job
    :param region_dimensions:
        Size (width x height) of each region to sample
    :param border_offset
        Offset to apply so that regions are only sampled this distance away
        from the border
    :return:
        None. Inserts records into the DB
    """
    region_width, region_height = region_dimensions

    job = LabelingJob()
    db.session.add(job)

    all_experiments_and_regions = _get_all_experiment_regions(
        artifact_dir=Path(app.config['ARTIFACT_DIR']),
        region_dimensions=region_dimensions, border_offset=border_offset)

    regions = np.random.choice(all_experiments_and_regions, size=n,
                               replace=False)

    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]

    for region in regions:
        experiment_id, region_x, region_y = region.split('_')
        region_x = int(region_x)
        region_y = int(region_y)
        job_region = JobRegion(job_id=job_id, experiment_id=experiment_id,
                               x=region_x, y=region_y, width=region_width,
                               height=region_height)
        db.session.add(job_region)

    db.session.commit()

    num_added = db.session.query(JobRegion).filter_by(job_id=job_id).count()
    print(f'Number of regions added to labeling job: {num_added}')


if __name__ == '__main__':
    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument('--config_path', required=True,
                            help='Path to app config')
        parser.add_argument('--n', required=True,
                            help='Number of regions to include in the '
                                 'labeling job')
        parser.add_argument('--region_width', required=True,
                            help='Region width', type=int)
        parser.add_argument('--region_height', required=True,
                            help='Region height', type=int)
        parser.add_argument('--border_offset', default=0, type=int,
                            help='Offset to apply so that regions are only '
                                 'sampled this distance away from the border')
        args = parser.parse_args()
        n = int(args.n)

        fov_width, fov_height = FIELD_OF_VIEW_DIMENSIONS
        if fov_width % args.region_width != 0:
            raise ValueError(f'Region width {args.region_width} not evenly '
                             f'divisible with field of view width {fov_width}')
        if fov_height % args.region_height != 0:
            raise ValueError(f'Region height {args.region_height} not evenly '
                             f'divisible with field of view width '
                             f'{fov_height}')

        region_dimension = (args.region_width, args.region_height)
        config_path = Path(args.config_path)

        app = create_app(config_file=config_path)
        if not Path(app.config['SQLALCHEMY_DATABASE_URI']
                    .replace('sqlite:///', '')).is_file():
            with app.app_context():
                db.create_all()
        app.app_context().push()
        populate_labeling_job(app=app, db=db, n=n,
                              region_dimensions=region_dimension,
                              border_offset=args.border_offset)

    main()
