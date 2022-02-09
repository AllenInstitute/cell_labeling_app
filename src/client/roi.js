class ROI {
    constructor({id, experiment_id, color, classifier_score=null, label=null, point=null, contour=null}={}) {
        this.id = id;
        this.experiment_id = experiment_id;
        this.color = color;
        this.classifier_score = classifier_score;
        this.label = label;
        this.point = point;
        this.contour = contour;
    }
}

export {
    ROI
}