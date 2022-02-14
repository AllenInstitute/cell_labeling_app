import argparse
import os
import re
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
from flask import Flask
from sqlalchemy import desc

from server.database.database import db
from server.database.schemas import LabelingJob, JobRegion
from server.main import create_app

FIELD_OF_VIEW_DIMENSIONS = (512, 512)


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
        dimensions. Ie if the field of view is 512x512, and region_divisor is
        4, the regions will be of size 128x128.
    """
    res = []
    fov_width, fov_height = FIELD_OF_VIEW_DIMENSIONS

    if exclude_motion_border:
        border_offset_x, border_offset_y = _get_motion_border_for_experiment(
            experiment_id=experiment_id,
            motion_correction_path=motion_correction_path)
    else:
        border_offset_x, border_offset_y = 0, 0

    fov_width -= border_offset_x * 2  # subtracting off both sides
    fov_height -= border_offset_y * 2  # subtracting off both sides

    region_width, region_height = (int(fov_width / fov_divisor),
                                   int(fov_height / fov_divisor))

    for y in range(border_offset_y, fov_height - border_offset_y,
                   region_height):
        for x in range(border_offset_x, fov_width - border_offset_x,
                       region_width):
            region = Region(x=x,
                            y=y,
                            width=region_width,
                            height=region_height,
                            experiment_id=experiment_id)
            res.append(region)
    return res


def _get_all_regions(
        artifact_dir: Path,
        motion_correction_path: Path,
        exclude_motion_border=True,
        fov_divisor=4
) -> List[Region]:
    """Returns list of all experiment-region combinations in string form
    :param artifact_dir:
        Path to artifact hdf5 files
    :param motion_correction_path
        Path to motion correction output
    :param exclude_motion_border
        Whether to exclude the motion border when sampling regions
    :param
        See `fov_divisor` in `_get_all_regions_for_experiment`
    """
    experiments = _get_all_experiments(artifact_dir=artifact_dir)

    res = []
    for experiment in experiments:
        regions = _get_all_regions_for_experiment(
            experiment_id=experiment,
            motion_correction_path=motion_correction_path,
            fov_divisor=fov_divisor,
            exclude_motion_border=exclude_motion_border
        )
        for region in regions:
            res.append(region)
    return res


def populate_labeling_job(
    app: Flask,
    db,
    n: int,
    motion_correction_path: Optional[Path],
    exclude_motion_border=True,
    fov_divisor=4
):
    """
    Creates a new labeling job by randomly sampling n total regions from all
    available experiments
    :param app:
        The flask app
    :param db:
        The database
    :param n:
        Number of regions in this job
    :param motion_correction_path
        Motion correction path. Required if exclude_motion_border is True.
    :param exclude_motion_border
        Whether to exclude the motion border when sampling regions
    :param fov_divisor
        The number of times to divide a field of view to get the region
        dimensions. Ie if the field of view is 512x512, and region_divisor is
        4, the regions will be of size 128x128.
    :return:
        None. Inserts records into the DB
    """
    if exclude_motion_border and motion_correction_path is None:
        raise ValueError('motion_correction_path required if '
                         'exclude_motion_border is True')
    job = LabelingJob()
    db.session.add(job)

    all_regions = _get_all_regions(
        artifact_dir=Path(app.config['ARTIFACT_DIR']),
        exclude_motion_border=exclude_motion_border,
        motion_correction_path=motion_correction_path,
        fov_divisor=fov_divisor
    )

    regions: List[Region] = \
        np.random.choice(all_regions, size=n, replace=False)

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
    print(f'Number of regions added to labeling job: {num_added}')


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
        parser.add_argument('--motion_correction_path', required=False,
                            help='Path to motion correction output. Used for '
                                 'sampling within motion border. Required if '
                                 'exclude_motion_border is True')
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
        populate_labeling_job(app=app, db=db, n=n,
                              exclude_motion_border=args.exclude_motion_border,
                              motion_correction_path=motion_correction_path,
                              fov_divisor=args.fov_divisor)


    main()
