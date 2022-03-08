import logging
import os
import shutil
import time
from pathlib import Path

import flask
import numpy as np
from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import UserLabels

logger = logging.getLogger(__name__)


class BackupManager:
    """Backup manager"""
    def __init__(self,
                 app: flask.Flask,
                 database_path: Path,
                 backup_dir: Path,
                 frequency: int = 60 * 5):
        """
        :param app
            The flask app, in order to query db
        :param database_path
            Path to sqlite database
        :param backup_dir:
            Where to write backups
        :param frequency:
            Frequency in seconds to check if a backup should be made
        """
        self._app = app
        self._database_path = database_path
        self._backup_dir = backup_dir
        self._frequency = frequency
        with self._app.app_context():
            self._num_records = self._get_num_label_records()
        os.makedirs(backup_dir, exist_ok=True)

    def run(self):
        """Checks to see if there have been new labels added since last time.
        If so, deletes previous backup and writes new one.
        Checks every self._frequency seconds"""
        with self._app.app_context():
            while True:
                num_records = self._get_num_label_records()
                if num_records > self._num_records:
                    logger.info(
                        f'Current number of label records: {num_records}, '
                        f'previous: {self._num_records}.')
                    self._make_backup()
                    self._cleanup_backups()
                    self._num_records = num_records
                time.sleep(self._frequency)

    def _make_backup(self):
        backup_path = self._backup_dir / f'{self._database_path.stem}_' \
                      f'{int(time.time())}.db'
        shutil.copy(self._database_path, backup_path)
        logger.info(f'Created new backup {backup_path}')

    def _cleanup_backups(self, retention_count: int = 1):
        """
        Deletes old backups

        :param retention_count:
            The number of backups to retain
        :return:
            None, deletes files inplace
        """
        backups = os.listdir(self._backup_dir)
        mod_times = [os.path.getmtime(self._backup_dir / file)
                     for file in backups]
        backups_idx_by_time = np.argsort(mod_times)
        for idx in backups_idx_by_time[:-retention_count]:
            os.remove(self._backup_dir / backups[idx])

    @staticmethod
    def _get_num_label_records():
        num_records = db.session.query(
            UserLabels
        ).count()
        return num_records
