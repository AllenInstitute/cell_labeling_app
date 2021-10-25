import argparse
import json
import os
import re
from pathlib import Path
from typing import List

import h5py
import numpy as np
from flask import Flask
from sqlalchemy import desc

from src.server.database.database import db
from src.server.database.schemas import LabelingJob, JobRois
from src.server.main import create_app


def _get_all_experiments_and_roi_ids(artifact_dir: Path) -> \
        List[str]:
    """
    Iterates through all available experiments, and returns a list of all
    experiment/roi_id combinations

    :param artifact_dir:
        Path to artifact hdf5 files
    :return:
        list of all experiment/roi_id combinations
    """
    res = []
    experiments = os.listdir(artifact_dir)
    for experiment in experiments:
        experiment_id = re.match('\d+', experiment).group()
        path = artifact_dir / experiment
        with h5py.File(path, 'r') as f:
            rois = json.loads(f['rois'][()])
            for roi in rois:
                # Concatenate the experiment and roi id to get single id
                id = f'{experiment_id}_{roi["id"]}'
                res.append(id)
    return res


def populate_labeling_job(app: Flask, db, n):
    """
    Creates a new labeling job by randomly sampling n total rois from all
    available experiments
    :param app:
        The flask app
    :param db:
        The database
    :param n:
        Number of rois in this job
    :return:
        None
    """
    job = LabelingJob()
    db.session.add(job)

    all_experiments_and_rois = _get_all_experiments_and_roi_ids(
        artifact_dir=Path(app.config['ARTIFACT_DIR']))

    rois = np.random.choice(all_experiments_and_rois, size=n, replace=False)

    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]

    for id in rois:
        experiment_id, roi_id = id.split('_')
        roi_id = int(roi_id)
        job_roi = JobRois(job_id=job_id, experiment_id=experiment_id,
                          roi_id=roi_id)
        db.session.add(job_roi)

    db.session.commit()

    num_added = db.session.query(JobRois).filter_by(job_id=job_id).count()
    print(f'Number of rois added to labeling job: {num_added}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', required=True, help='Path to app '
                                                             'config')
    parser.add_argument('--n', required=True,
                        help='Number of rois to include in the labeling job')
    args = parser.parse_args()
    n = int(args.n)
    config_path = Path(args.config_path)

    app = create_app(config_file=config_path)
    app.app_context().push()
    populate_labeling_job(app=app, db=db, n=n)
