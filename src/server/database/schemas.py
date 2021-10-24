import datetime

from flask_login import UserMixin

from src.server.database.database import db


class LabelingJob(db.Model):
    job_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class JobRois(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey(LabelingJob.job_id))
    experiment_id = db.Column(db.String, nullable=False)
    roi_id = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'id: {self.id}, job_id: {self.job_id}, experiment_id: ' \
               f'{self.experiment_id}, roi_id: {self.roi_id}'


class User(UserMixin, db.Model):
    id = db.Column(db.String, primary_key=True)


class UserLabel(db.Model):
    user_id = db.Column(db.String, db.ForeignKey(User.id),
                        primary_key=True)
    job_roi_id = db.Column(db.Integer, db.ForeignKey(JobRois.id),
                           primary_key=True)
    label = db.Column(db.String, nullable=False)
