class ROI {
    constructor({id, experiment_id, color, classifier_score=null, label=null, point=null, contours=null,
                box_x=null, box_y=null, box_width=null, box_height=null}={}) {
        this.id = id;
        this.experiment_id = experiment_id;
        this.color = color;
        this.classifier_score = classifier_score;
        this.label = label;
        this.point = point;
        this.contours = contours;
        this.box_x = box_x;
        this.box_y = box_y;
        this.box_width = box_width;
        this.box_height = box_height;
    }
}

export {
    ROI
}