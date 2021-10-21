from sqlalchemy import desc

from app import db, LabelingJob, JobRois, User


def create_db():
    db.create_all()


def populate_users():
    users = ('adam.amster', 'scott.daniel', 'wayne.wakeman', 'michael.wang')
    for user in users:
        user = User(user_id=user)
        db.session.add(user)
    db.session.commit()


def populate_labeling_job():
    job = LabelingJob()
    db.session.add(job)

    rois_to_label = [
        {
            'experiment_id': '785569423',
            'roi_id': 0},
        {
            'experiment_id': '774392903',
            'roi_id': 0
        }
    ]

    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).scalar()

    for roi in rois_to_label:
        job_roi = JobRois(job_id=job_id, experiment_id=roi[
            'experiment_id'], roi_id=roi['roi_id'])
        db.session.add(job_roi)

    db.session.commit()

    print(JobRois.query.all())


if __name__ == '__main__':
    create_db()
    populate_users()
    populate_labeling_job()
